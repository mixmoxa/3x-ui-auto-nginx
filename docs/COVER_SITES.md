# Static cover sites

New installations select one supplied A template for the panel domain and one B
for REALITY. Optional Vision gets a different B template. Each site is generated
once from the reviewed variants using Python secrets. This improves ordinary
public HTTP content; it is not a proven defense against DPI, active probing or
IP blocking.

Sites live under /var/www/html/cover-panel, cover-reality and optional cover-vision.
The private /etc/x-ui/cover-sites.json records selections, never credentials.
Backup v3 preserves the sites and selections; Restore and Change Domains do not
regenerate content. Existing legacy sites are not migrated automatically.

Templates A1–A3 are selected for the panel; B1–B3 for REALITY, with Vision
choosing one of the two remaining B templates. Brand (6), palette (4), artwork
(3), and copy kit (2) are selected independently using standard-library secrets.
Templates and personalization data stay in private staging, not document roots.
Public sites contain HTML, local CSS/JS/SVG, favicons and robots.txt only.

The installer pins its source commit using the existing source comparison,
then downloads one GitHub source archive for that SHA and extracts only the
cover resources. Site preparation/validation and conflict checks precede managed
cleanup. Publication refuses symlinked parents and foreign cover paths. The
selection file is root:root 0600; generated directories/files are 0755/0644.

Static 404 handling is scoped to the static location; proxied service error
contracts are preserved. New installations serve root /assets routes on the panel domain only;
native subscription HTML resources under its subscription prefix still work on
both supported subscription domains. Network
listeners, TLS termination, PROXY protocol, transport paths and client secrets
are unchanged. New Vision uses cover-vision; its recognizer also accepts the
exact legacy /var/www/html layout. Verified Vision rollback removes only a newly
created, unchanged Vision site and its selection, preserving both core sites.

The supplied archive SHA-256 is
e655164fa862046c781bf934fce9c9ce0dd220a57dae030211a1cf716ad3087c.
Templates, variants, generator and applicable standard-library checks are carried
without design/content changes. Demo builds, screenshots and browser dependencies
are excluded. A confirmed full reinstall removes the three owned cover-panel,
cover-reality and cover-vision directories together with their state, after the
foreign-path preflight; no additional website tree outside /var/www/html is claimed.
