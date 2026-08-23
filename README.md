## What

Run [Odoo](https://www.odoo.com/) on [Cloudron](https://cloudron.io). For more information see DESCRIPTION.md

## Why

Because Odoo works almost out of the box in any system that has Postgres and some disk space for data storage.


## Build and Install

- Install Cloudron CLI on your machine: `npm install -g cloudron-cli`.
- Install Docker, and make sure you can push to docker hub, or install the docker registry app in your own Cloudron.
- Log in to your Cloudron using cloudron cli: `cloudron login <my.yourdomain.tld>`.
- Build and publish the docker image: `cloudron build`.
- If you're using your own docker registry, name the image properly,
  like `docker.example-cloudron.tld/john_doe/cloudron-odoo`.
- Log in to Docker Hub and mark the image as public, if necessary.
- Install the app `cloudron install -l <auth.yourdomain.tld>`
- Look at the logs to see if everything is going as planned.

Refer to the [Cloudron Docs](https://docs.cloudron.io/packaging/cli) for more information.

## Third-party Intellectual Properties

This repository is heavy inspired by https://github.com/njsubedi/cloudron-odoo thanks !
This repository use the same technic as doodba, an odoo docker image, so thanks to https://github.com/Tecnativa/doodba !
## Maintenance : CLI jarvis

L'image embarque le CLI `jarvis` (identique à celui des images
`odoo_jarvis_assistant`) : `jarvis backup`, `jarvis restore`, `jarvis shell`,
`jarvis module`, `jarvis remote`. Le mot de passe maître et le répertoire de
sauvegarde se configurent dans `/app/data/.jarvis`.
