# Project Website

This is the optional KubePACS website, not an experiment runner. Source lives
under `src/app/`. The project uses Next.js 16.1.6 and React 19.2.3, with a
static export configured in `next.config.mjs`.

## Development And Build

Use Node.js 24 (the CI version) and npm. From the repository root:

```sh
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
```

Dependency installation and any build-time external assets require network
access. A successful build exits with code 0 and produces `frontend/out/`.
This check validates the website build, not KubePACS results.

The documentation check passed on Node 24.11.1, with one lint warning about
the image element. Dependency auditing reported vulnerabilities, including
a critical finding; review `npm audit` before deployment. These were not
remediated as part of the documentation changes, and a static build pass
does not imply that development/build dependencies are secure.

For development:

```sh
npm --prefix frontend run dev -- --port 3000
```

For a local preview of the built static export:

```sh
python3 -m http.server 3000 --directory frontend/out
```

Open [the local site](http://localhost:3000). Choose another free port if
needed; stop the preview with Ctrl-C. Do not use `npm start` for the exported
site: that package script invokes `next start`, while this project uses
`output: 'export'`.

Deployment uses the [AWS publication workflow](../.github/workflows/deploy-frontend.yaml) and requires
maintainer credentials. Publication is not part of artifact evaluation and
must not be necessary to reproduce figures. Generated `out/`, `.next/`,
and installed `node_modules/` can be removed when no longer needed.
