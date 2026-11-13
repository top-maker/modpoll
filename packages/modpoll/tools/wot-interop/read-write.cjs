// Actual node-wot Consumer: no project extension interpreter or value conversion.
const fs = require('node:fs');
const { Servient } = require('@node-wot/core');
const { ModbusClientFactory } = require('@node-wot/binding-modbus');
(async () => {
  const servient = new Servient();
  servient.addClientFactory(new ModbusClientFactory());
  try {
    const WoT = await servient.start();
    const thing = await WoT.consume(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
    const writes = JSON.parse(process.argv[3] || '{}');
    for (const [name, value] of Object.entries(writes)) await thing.writeProperty(name, value);
    const values = {};
    for (const name of Object.keys(thing.getThingDescription().properties)) {
      if (!thing.getThingDescription().properties[name].writeOnly)
        values[name] = await (await thing.readProperty(name)).value();
    }
    console.log('RESULT=' + JSON.stringify(values));
  } finally {
    await servient.shutdown();
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
