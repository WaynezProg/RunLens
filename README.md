# RunLens

RunLens is a filesystem-first artifact protocol and CLI for coding agents.

The MVP manages `.agent-artifacts/`, renders static HTML reports, and only writes
`.agent-artifacts/deliverables/final.html` after required acceptance criteria in
`artifact_spec.yaml` pass with evidence.

## MVP Commands

~~~bash
runlens init
runlens update --state working --note "Implemented parser"
runlens render
runlens checkpoint --reason "Useful progress before tests"
runlens finalize
runlens finalize --blocked-reason "Missing access token"
~~~
