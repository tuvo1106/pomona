# Security

## What this thing is, threat-model-wise

Pomona is a local program. There is no server it talks to, no account, no API key, no telemetry,
and nothing is uploaded. It reads an Apple Health export off your disk, writes a SQLite file next
to it, and serves a web page from `127.0.0.1`. So most of the questions a security policy usually
answers — how is data encrypted in transit, who can access the database, what happens on a breach
— don't have an interesting answer here: the data never leaves your machine, and the database is
a file you own.

The one exception is stated in the README and in
[ADR-0004](docs/adr/0004-openstreetmap-tiles-for-routes-map.md): the Routes tab can fetch map
tiles from OpenStreetMap, which tells that server which map squares you're looking at. **It is off
by default**, and with it off the app makes no request outside its own origin.

## What would count as a vulnerability

Things that would genuinely matter, and are worth reporting:

- Anything that causes health data to leave the machine — an unexpected outbound request, a
  third-party script, data in a URL that gets logged somewhere.
- Serving files outside `frontend/dist/` through the static mount, or reading files outside the
  paths given on the command line.
- Injection through export content: the export is parsed and then rendered, so a value that
  escapes into SQL or into the DOM as markup would be a real finding.
- Binding to a non-loopback interface, or making the API reachable off the machine, without the
  operator asking for it.

## Known, accepted, and not a vulnerability

**Ingesting an export you did not create can be made to hang or exhaust memory.** `export.xml` is
parsed with Python's standard-library `xml.etree.ElementTree`, which expands internal entities —
verified, a four-level ten-way nesting produced a 10,000-character attribute — so a crafted file
can use the classic entity-expansion trick to blow up memory. It does **not** resolve external
entities: `<!ENTITY x SYSTEM "file:///etc/passwd">` is refused with a `ParseError`, so there is no
file disclosure and no outbound fetch, only denial of service against yourself.

This is accepted rather than fixed because the input is your own export, from Apple, that you
chose. If you are ingesting an export somebody sent you, that is a different situation, and
running it in a container is the sensible answer. Reports that amount to "a malicious XML file
can slow this down" will be closed with a link to this paragraph.

Also not vulnerabilities: the app having no authentication (it serves loopback only, to you);
the database being unencrypted (it is a file in your filesystem, with your filesystem's
permissions); dependency advisories with no reachable path from this code.

## Reporting something

Use GitHub's private vulnerability reporting: the **Security** tab of this repository →
**Report a vulnerability**. That opens a channel only the maintainer can see, so the report stays
private until there's a fix.

If that button isn't there, it means the setting hasn't been enabled — which is a mistake on my
part, not an invitation to post the details publicly. Open an ordinary issue containing nothing
but "I have a security report, please enable private vulnerability reporting", and wait.

Please **do not include your own health data** in a report. If you need to show the shape of the
data that triggered it, generate a synthetic export and use that instead:

```bash
uv run python scripts/make_demo_export.py
```

If the report needs a file to reproduce, a minimal hand-written XML fragment is better than an
excerpt from a real export. See [docs/YOUR-DATA.md](docs/YOUR-DATA.md) for what the export
contains, if you need to construct one.

## What to expect

One maintainer, no bounty, best effort. You'll get an acknowledgement, and either a fix or a
reasoned explanation of why it isn't one. Nothing here is under a service level agreement.
