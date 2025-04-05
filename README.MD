# This repo holds the files for OmniVaultX
This is a masters thesis project, so everything here is work in progress.

## https://omnivaultx.com/

# Basic setup
0. (Optional) Install docker
```bash
sudo ./docker-setup.sh
```

1. Install CLI
```bash
cd CLI_versions
sudo dpkg -i om_v1_amd64.deb
```

2. Create .env
```bash
sudo mv .env.example .env
```

3. Run the app with docker
```bash
sudo ./start_image.sh
```

# Post setup
1. Disable auth for CLI
```bash
om -noauth
```

2. Set API for CLI
```bash
om --setapi localhost:80 
```

3. Test the CLI and connection to the backend
```bash
om --lc
```

4. For any help open help
```bash
om --help
```