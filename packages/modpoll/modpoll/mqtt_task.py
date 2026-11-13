import logging
import queue
import socket
import ssl
import threading
import time
from typing import Optional, Tuple, List

from paho.mqtt.client import (
    Client as MQTTClient,
    CallbackAPIVersion,
    ReasonCode,
    MQTTProtocolVersion,
    MQTTMessageInfo,
)
from paho.mqtt import MQTTException


class MqttHandler:
    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        user: Optional[str],
        password: Optional[str],
        clientid: Optional[str],
        qos: int,
        subscribe_topics: Optional[List[str]] = None,
        use_tls: bool = False,
        tls_version: str = "tlsv1.2",
        cacerts: Optional[str] = None,
        insecure: bool = False,
        mqtt_version: str = "5.0",
        log_level: str = "INFO",
    ):
        self.name = name
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.clientid = clientid
        self.qos = qos
        self.subscribe_topics = subscribe_topics or []
        self.use_tls = use_tls
        self.tls_version = tls_version
        self.cacerts = cacerts
        self.insecure = insecure
        self.mqtt_version = mqtt_version
        self.loglevel = log_level

        self.mqtt_client: Optional[MQTTClient] = None
        self.clean_start_or_session = qos == 0
        self.rx_queue = queue.Queue(maxsize=1000)
        self.logger = logging.getLogger(__name__)
        self._connack_event = threading.Event()
        self._connack_success = False
        self._network_loop_started = False
        self.connack_timeout = 10.0
        self.close_timeout = 5.0
        self.unpublished_count = 0
        self._pending_publishes = []

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if isinstance(flags, dict):  # MQTTv5
            session_present = flags.get("session present", False)
        else:  # MQTTv3
            session_present = flags.session_present

        if isinstance(reason_code, ReasonCode):
            rc = reason_code.value
        else:
            rc = reason_code

        self._connack_success = rc == 0
        self._connack_event.set()
        if rc == 0:
            self.logger.debug("Connected to MQTT broker.")
            if session_present:
                self.logger.info("MQTT session present, reusing existing session")
            else:
                self.logger.info("Created new MQTT session.")
                for topic in self.subscribe_topics:
                    self.logger.info(
                        f"Subscribe to topic: {topic} with QoS: {self.qos}"
                    )
                    client.subscribe(topic, self.qos)
        else:
            self.logger.warning(f"Connection failed with reason code: {rc}")

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if isinstance(reason_codes, int):
            reason_codes = [reason_codes]
        for rc in reason_codes:
            if rc in (0, 1, 2):
                self.logger.info("Subscribed successfully.")
            else:
                self.logger.warning(f"Failed to subscribe. Reason code: {rc}")

    def _on_publish(self, client, userdata, mid, reason_codes, properties):
        self.logger.debug(f"Message (mid={mid}) published successfully.")

    def _on_message(self, client, userdata, message):
        kind = "retained message" if message.retain else "message"
        self.logger.info(f"Receive {kind} ({message.topic})")
        self.logger.debug(
            f"Receive {kind} payload ({message.topic}): {message.payload}"
        )
        msg = (message.topic, message.payload, bool(message.retain))
        try:
            self.rx_queue.put(msg, block=False)
        except queue.Full:
            self.logger.warning("MQTT receiving queue is full, ignoring new message.")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connack_success = False
        if reason_code == 0:
            self.logger.info("Disconnected.")
        else:
            self.logger.warning(f"Disconnected with error, reason_code={reason_code}.")

    def _on_log(self, client, userdata, level, buf):
        self.logger.debug(f"{level} | {buf}")

    def _setup_tls(self):
        try:
            tls_versions = {
                "tlsv1.2": ssl.PROTOCOL_TLSv1_2,
                "tlsv1.1": ssl.PROTOCOL_TLSv1_1,
                "tlsv1": ssl.PROTOCOL_TLSv1,
            }
            tlsVersion = tls_versions.get(self.tls_version.lower(), ssl.PROTOCOL_TLS)
            cert_required = ssl.CERT_NONE if self.insecure else ssl.CERT_REQUIRED
            self.mqtt_client.tls_set(
                ca_certs=self.cacerts,
                certfile=None,
                keyfile=None,
                cert_reqs=cert_required,
                tls_version=tlsVersion,
                ciphers=None,
            )
        except ssl.SSLError as ssl_ex:
            self.logger.error(f"SSL setup error: {ssl_ex}")
            raise
        except Exception as ex:
            self.logger.error(f"TLS setup error: {ex}")
            raise

    def setup(self) -> bool:
        try:
            clientid = self.clientid or ("" if self.qos == 0 else socket.gethostname())

            if self.mqtt_version == "5.0":
                self.mqtt_client = MQTTClient(
                    CallbackAPIVersion.VERSION2,
                    client_id=clientid,
                    protocol=MQTTProtocolVersion.MQTTv5,
                )
            else:
                self.mqtt_client = MQTTClient(
                    CallbackAPIVersion.VERSION2,
                    client_id=clientid,
                    clean_session=self.clean_start_or_session,
                    protocol=MQTTProtocolVersion.MQTTv311,
                )

            self.mqtt_client.max_queued_messages_set(1000)

            if self.use_tls:
                self._setup_tls()

            if self.user:
                self.mqtt_client.username_pw_set(self.user, self.password)

            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_subscribe = self._on_subscribe
            self.mqtt_client.on_message = self._on_message
            self.mqtt_client.on_publish = self._on_publish
            self.mqtt_client.on_disconnect = self._on_disconnect
            if self.loglevel.upper() == "DEBUG":
                self.mqtt_client.on_log = self._on_log

            return True
        except Exception as ex:
            self.logger.error(f"MQTT client setup error: {ex}")
            return False

    def connect(self) -> bool:
        if not self.mqtt_client:
            self.logger.error("MQTT client not initialized. Call setup() first.")
            return False
        if self.is_connected():
            return True
        if self._network_loop_started:
            # Paho owns reconnects after loop_start; do not start a second loop.
            return False

        self._connack_event.clear()
        self._connack_success = False
        try:
            connect_kwargs = {
                "host": self.host,
                "port": self.port,
                "keepalive": 60,
            }
            if self.mqtt_version == "5.0":
                connect_kwargs["clean_start"] = self.clean_start_or_session

            self.mqtt_client.connect(**connect_kwargs)
            self.mqtt_client.loop_start()
            self._network_loop_started = True
            if not self._connack_event.wait(self.connack_timeout):
                self.logger.warning("Timed out waiting for MQTT CONNACK.")
                return False
            return self._connack_success
        except (OSError, MQTTException) as ex:
            self.logger.error(f"MQTT connection error: {ex}")
            return False

    def publish(
        self, topic: str, msg: str, qos: Optional[int] = None, retain: bool = False
    ) -> Optional[MQTTMessageInfo]:
        if not self.mqtt_client:
            self.logger.error("MQTT client not initialized. Call setup() first.")
            return None

        qos = self.qos if qos is None else qos

        if not self.mqtt_client.is_connected():
            if qos == 0:
                self.logger.warning(
                    "MQTT client not connected and QoS is 0, skipping publish"
                )
                return None
            self.logger.warning("MQTT client not connected, attempting to reconnect")
            if not self.connect():
                return None

        try:
            pubinfo = self.mqtt_client.publish(topic, msg, qos, retain)
            if isinstance(pubinfo, MQTTMessageInfo) and pubinfo.rc == 0:
                self._pending_publishes = [
                    info for info in self._pending_publishes if not info.is_published()
                ]
                self._pending_publishes.append(pubinfo)
            elif pubinfo.rc != 0:
                self.logger.warning("MQTT publication rejected with RC %s", pubinfo.rc)
            self.logger.debug(
                f"Publishing MQTT topic: {topic}, msg: {msg}, qos: {qos}, RC: {pubinfo.rc}"
            )
            self.logger.info(f"Publish message to topic: {topic}")
            return pubinfo
        except MQTTException as ex:
            self.logger.error(
                f"Failed to publish MQTT topic: {topic}, msg: {msg}, qos: {qos}. Error: {ex}"
            )
            return None

    def receive(self) -> Tuple[Optional[str], Optional[bytes], bool]:
        try:
            topic, payload, retained = self.rx_queue.get(block=False)
            return topic, payload, retained
        except queue.Empty:
            return None, None, False

    def is_connected(self) -> bool:
        return self.mqtt_client is not None and self.mqtt_client.is_connected()

    def close(self) -> None:
        if not self.mqtt_client:
            return
        deadline = time.monotonic() + self.close_timeout
        for info in self._pending_publishes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                info.wait_for_publish(timeout=remaining)
            except (RuntimeError, ValueError) as exc:
                self.logger.warning("Unable to flush MQTT publication: %s", exc)
                break
        self.unpublished_count = sum(
            not info.is_published() for info in self._pending_publishes
        )
        if self.unpublished_count:
            self.logger.warning(
                "Closing MQTT with %s unacknowledged publication(s)",
                self.unpublished_count,
            )
        try:
            # Disconnect before joining: loop_stop alone can wait indefinitely
            # for QoS handshakes when a peer stops acknowledging publications.
            self.mqtt_client.disconnect()
        except MQTTException as exc:
            self.logger.error("Error during MQTT client closure: %s", exc)
        finally:
            self.mqtt_client.loop_stop()
            self._network_loop_started = False
            self._pending_publishes.clear()
