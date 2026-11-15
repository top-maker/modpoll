# Verification reports

Adding `--report` to a normal read verifies a Thing Model on real hardware. Every point is read once, read-only,
without retries and with a timeout of at most 10 seconds, so a lost request is a result and not something to
repeat. `--report FILE` writes the verification report (`-` prints it); a bare `--report` asks where to save,
whether the values look right, and whether to upload:

```sh
modpoll --config examples/modsim.tm.json --tcp 192.168.1.20 --unit-id 3 --report report.json
```

The report records, for each point, whether the read worked (`ok`, a Modbus `exception` with its code,
`no-response`, or `not-tested` when the answer could not be decoded) and your judgment of the value:
`--confirm POINT...` (or `all`) and `--reject POINT...` for values you compared with the device, otherwise
`unchecked`. The report holds no address, Unit ID, serial number or value; review it before sharing. Check it
with `modpoll-wot validate-report report.json --model model.tm.json` (see the
[report schema](../reference/modpoll-wot/profile.md#verification-reports)). `--export` still writes the snapshot
of the same read.

A point whose DataSchema declares `const` (an identity point, such as a meter code) is compared with the value
read, and the report records only `match` or `mismatch`.

When a read fails, modpoll lists each failed group as the device answered it, without guessing why:

```text
Group 3 of 8 (holding registers 40-59): exception code 02 (illegal data address).
Group 5 of 8 (input registers 0-59): no response.
Groups 6-8 of 8: not tried.
Not a full read: 21 of 44 points read.
```

## Upload to ModioHub

Only a full read whose identity points match can be uploaded. Any other report is saved for your own checks or a
catalog request, and `--upload` refuses it without contacting ModioHub. The exit code is 1 unless the report can
be uploaded.

ModioHub identifies the product from the model fingerprint. When it does not know the model, modpoll names the
product whose baseline Thing Model holds all of the report's points, or lets you choose one from the matched
products or a search, and otherwise prints a prefilled catalog request.

`modpoll --config ... --upload` shows the report and, after you confirm (or with `--yes`), uploads it. Without a
login the sign-in flow starts right there:

```sh
modpoll --config modiohub:k3x9f2m7q4a8n5bd@latest --tcp 192.168.1.20 --upload
```

## Sign in to ModioHub

`modpoll login` (or `modsim login`) signs in with your browser: it prints a code and an address (and opens the
address where a browser can open), you confirm the code there, and the 7-day tool session is kept in a file only
you can read (`~/.config/modiohub/credentials.json`, or `%APPDATA%\modiohub` on Windows). Both tools use the same
file, so signing in with either signs in both. `MODIOHUB_TOKEN` in the environment replaces the file for scripts,
`MODIOHUB_URL` selects another server, and `login` and `logout` take `--server URL` for the same. `logout` forgets
the login on this computer; revoke the session in your ModioHub settings to end it on the server.

Once signed in, `--config modiohub:<id>@<version>` (the version is a number or `latest`) reads one of your custom
Thing Models. A shared one needs no login. Verifying it names the Workspace model in the report.
