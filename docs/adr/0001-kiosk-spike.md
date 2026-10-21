# ADR-0001: Kiosk spike is recorded, not applied on the build machine

Cage without `-s`, greetd autologin, Chromium policy, polkit, logind, and sysctl files ship in `packaging/`. This repository does not apply them to the development machine. Whether cage stacks GCompris, whether `grim` captures frames, and whether PipeWire's monitor source can be recorded stay as hardware checks for the Toughbook. The session agent tests the allowlist, the localhost kiosk URL, and the two-second browser restart in software.
