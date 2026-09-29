# Security and deployment

The default RTSP listener and companion HTTP server bind to loopback. They are development services, not hardened Internet-facing endpoints. The RTSP configuration has no authentication in its local-only configuration.

For LAN access, explicitly configure MediaMTX authentication, publishing permissions, and interface/firewall scope. Keep the companion command server local; shutter commands affect all video consumers. Never forward these ports directly to the public Internet.

For YouTube, let OBS publish outbound using your account or stream key. Do not place credentials in source code, issue reports, screenshots, or committed configuration.

When reporting an issue, use the repository's private vulnerability-reporting option if its owner enables it. Do not publish an exploitable issue together with access credentials or private captures.
