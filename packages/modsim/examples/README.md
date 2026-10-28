# Device examples and vendor references

- [ADAM-5017UH through ADAM-5000L/TCP](adam-5017uh/): first physical-reference
  candidate, confirmed slot 0, eight raw analog input words.
- [ADAM-6024](adam-6024/): second core I/O candidate, raw AI/AO and grouped DI/DO.
- `modsim.csv`: existing modpoll 1.x client mapping for the built-in simulator.

Each product directory keeps its TD beside the original vendor PDFs, source URLs,
SHA-256 hashes and assumptions. Raw TDs preserve register words while physical
scaling and device-specific addressing are being confirmed. A successful offline
validation is evidence of the configuration contract, not hardware correctness.
The current modsim 1.x runtime still uses its built-in datastore; TD runtime loading
is planned for v2. Offline validation uses the independently published
`modpoll-wot==0.1.0a1` package; it does not connect to a device.
