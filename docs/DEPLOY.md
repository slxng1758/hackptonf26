# Deploy on Vultr

One server runs everything: the API, the web app, and Chromium for the customers' browsing, in one Docker container
behind Caddy (HTTPS once a domain points at it). Files: `Dockerfile`, `deploy/`.

## 1. Server (once, ~5 min)

1. Sign up at vultr.com and claim the hackathon credits (MLH's "Best Use of Vultr" page or the MLH coach has the link).
2. Add your SSH key: **Account → SSH Keys → Add**. Paste the output of `cat ~/.ssh/id_ed25519.pub`
   (no key yet? `ssh-keygen -t ed25519`, press Enter through the prompts).
3. **Deploy → Cloud Compute (Shared CPU)**:
   - Location: **New Jersey** (closest to Princeton)
   - Image: **Ubuntu 24.04 LTS x64**
   - Plan: **2 vCPU / 4 GB RAM** at least. Each customer runs its own Chromium; 1 GB plans run out of memory.
   - SSH key: the one you added
   - Additional features → **Cloud-Init User-Data**: paste all of `deploy/cloud-init.yaml`
   - Deploy. Note the server's **IP address**.
4. MongoDB Atlas → **Network Access → Add IP Address**: the server's IP (or `0.0.0.0/0`).

## 2. Deploy (and every redeploy)

From the repo root on your laptop, with your keys in `.env`:

```sh
./deploy/deploy.sh <server-ip>
```

It waits for Docker on the server, copies the code and `.env` over SSH (never through git), builds the container
(first build: a few minutes), starts it, and prints the URL: `http://<server-ip>`.

Run the same command again after pulling new code to redeploy. Simulations, screenshots and memory live in
`/root/app/runs` on the server and survive redeploys.

## 3. Domain + HTTPS (after the GoDaddy domain)

1. In GoDaddy DNS, add an **A record**: name `@`, value `<server-ip>` (and `www` the same if you like).
2. Wait until `dig +short yourdomain.xyz` prints the IP, then:

```sh
./deploy/deploy.sh <server-ip> yourdomain.xyz
```

Caddy gets a Let's Encrypt certificate on the first request: `https://yourdomain.xyz`.

## Useful commands

```sh
ssh root@<ip> 'cd /root/app && docker compose -f deploy/docker-compose.yml logs -f --tail 100 app'   # live logs
ssh root@<ip> 'cd /root/app && docker compose -f deploy/docker-compose.yml restart app'               # restart
ssh root@<ip> 'free -h; docker stats --no-stream'                                                      # memory
```

## Notes

- One worker on purpose: running simulations live in the server process's memory.
- Product pages for described products are browsed by Chromium inside the container at `http://localhost:4620`.
- Secrets: `.env` is copied with `scp` and set to mode 600 on the server. It is excluded from the Docker image
  (`.dockerignore`) and passed in at run time.
