# Github Project Deployer
This project is designed to act as the gateway between GitHub Actions and my personal devices connected to tailscale.

The reason this is being developed is to be the main chokepoint for Github Actions artifacts, and allow for deployment of code from my repositories to my devices without placing too much trust on github's control plane (although there would probably be bigger issues if Github Actions secrets got compromised at large)

Should, and if github actions turn malicious for any reason, this application can be quickly shut down, or Tailscale ACLs can be modified accordingly to deny access to any resources for any node that is CI, minimising damage in case it does happen

# Architecture
This project is inspired by how computers boot. When they boot, they usually go through this cycle:
```
Firmware --> OS
```

This project also aims to be like that, with a launcher.py file acting as the launcher for the main payload. However, the twist is that the launcher.py can get an updated payload at will (e.g. when triggered from github actions)

However, it will maintain it's own github repository and pull from github, rather than take artifacts from github directly. This is to enhance security, as if the CI node is compromised, or my tailscale auth key is compromised for any reason, untrusted code could be executed on my hardware which could be catastrophic.

Before running the payload, the launcher verifies that the git commit was made by me, and that it is signed with my verified signature. This should prevent many classes of attack within of itself.