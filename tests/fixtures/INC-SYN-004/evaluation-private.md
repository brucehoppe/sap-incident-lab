# Evaluation answer key — INC-SYN-004 (synthetic)

**Not read by the server.**

Known cause: the client SSL certificate `SYN_CLIENT_CERT` used by RFC
destination `SYN_PARTNER_01` expired at exactly 2026-09-12 00:00:00. Every
outbound call after that instant fails the TLS handshake identically, and
the previous call at 23:59:59 succeeded normally — a clean before/after
split at the certificate's own expiry timestamp, not a gradual
degradation. The gateway log names the exact certificate; the RFC trace
gives the exact expiry instant. A correct investigation should identify
the specific certificate and its expiry (not "network issue" or "partner
system down") and recommend renewing/rotating SYN_CLIENT_CERT via
STRUST, plus checking whether other destinations share it.
