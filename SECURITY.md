# Security

UplinkWitness is designed to run on a trusted local network.

## Dashboard exposure

The dashboard does not provide a public-Internet authentication layer. Do not expose port `8080` directly through router port forwarding.

For remote access, use a private VPN or mesh VPN.

## Sensitive data

Never commit or publish:

- FRITZ!Box credentials
- `.env` files containing secrets
- unredacted router event logs
- public IP addresses tied to a private installation
- other personal network information

## Reporting a vulnerability

If a security issue can be described without exposing user secrets, open a GitHub issue with enough information to reproduce it and clearly mark it as security-related.

For reports that necessarily contain sensitive information, do not post the sensitive material publicly; contact the maintainer through an appropriate private channel listed on the maintainer's GitHub profile.
