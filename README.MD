# This repo holds the files for OmniVaultX for public use
This is a masters thesis project, so everything here is work in progress.

## https://omnivaultx.com/

# Basic setup
0. (Optional) Install docker (You will be prompted if its not found)
```bash
sudo ./docker-setup.sh
```

1. Install CLI
```bash
cd CLI_versions
sudo dpkg -i om_v[X]_amd64.deb
```

2. Create .env
```bash
sudo mv .env.example .env
```
Open .env and replace the default encryption key with a 32 character long secret.


3. Run the app with docker or podman
```bash
sudo ./start_image.sh
```

# Post setup
1. Disable auth for CLI if not running min version from main app
```bash
om -noauth
```

1.1 Authenticate - only if not using min version
```bash
om --authenticate
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


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.