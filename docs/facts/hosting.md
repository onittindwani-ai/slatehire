# Hosting: Vercel, Railway, Hetzner

Checked 2026-11-22.

- Vercel VERIFIED: set the root directory to apps/web and turn on including source files outside the root so packages/ui-kit is built. Every workspace package must be listed in pnpm-workspace.yaml. Edge cases from community reports are UNVERIFIED.
- Railway VERIFIED: Config as Code (railway.json) is deprecated. Existing files work until 2026-12-01 and new services cannot opt in. Prefer dashboard settings. Fields: build.dockerfilePath, deploy.healthcheckPath, healthcheckTimeout, startCommand.
- Hetzner: cloud-init user data starts with #cloud-config. Keep secrets out of it. Attach an SSH key when you create the server. Firewall details are UNVERIFIED.
- None of the three was deployed to. No Docker daemon was available while writing this; the repository's CI workflow builds the images and starts the compose stack on a GitHub machine, which shows they build and start and nothing more. next build and the compose file check were run.
