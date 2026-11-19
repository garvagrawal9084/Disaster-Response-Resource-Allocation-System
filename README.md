# Disaster Response Resource Allocation System

DRRAS is a decision-support prototype for a coordinator planning ambulance allocations in simulated disasters. The dashboard maps affected areas and resource bases, runs a severity-first baseline and a constrained optimizer, and compares their saved results. The coordinator reviews the proposed assignments.

## Start the application

Install Docker with Compose, then run from the repository root:

```sh
docker compose up --build --wait -d
```

- Dashboard at <http://localhost:8080>
- Interactive API documentation at <http://localhost:8080/api/docs>
- Database readiness at <http://localhost:8080/api/health>

Select one of the three simulated scenarios. Run **Baseline** and **Optimized**, then open **Compare results**. The matrix is created on the first run. The dashboard flags straight-line estimates when road data is unavailable. OpenStreetMap tiles require internet access.

Open **Travel matrix** to inspect routing estimates, **Allocations** to see unmet ambulance demand by area, and **Run history** to revisit plans from earlier scenario revisions.

Stop the stack with `docker compose down`. The named database volume keeps scenarios and results across restarts.

## Project guide

- [Software design report](<Document/DRRAS Software Design Report.docx>) and [software testing report](<Document/DRRAS Software Testing Report.docx>) are professor-facing reports.
- The numbered professor-facing set now includes the [SRS](<Document/06 - DRRAS_SRS.pdf>), [architecture style report](<Document/07 - DRRAS Architecture Style Report.pdf>), [black box report](<Document/12 - DRRAS Black Box Testing Report.docx>), [white box report](<Document/13 - DRRAS White Box Testing Report.docx>), and [activity diagram report](<Document/14 - DRRAS Activity Diagram Report.docx>).
- [Personal project guide](<docs/DRRAS Personal Project Guide.docx>) explains the project and Pratibha's white box result in plain language. The numbered study guides and internal draw.io references are in `docs/`.
- [Documentation index](docs/DRRAS_README.drawio) lists the project guides and editable internal draw.io references.
- [Backend and database walkthrough](docs/DRRAS_backend.drawio) explains the workflow, schema, API, solver, and how to modify the implementation.
- [Frontend behavior](docs/DRRAS_frontend.drawio) describes the dashboard and its API integration.
- [Docker and local development](docs/DRRAS_docker.drawio) covers ports, settings, startup, and logs.
- [Change log](docs/DRRAS_changes.drawio) records the implementation and its verification.
- [Original requirements](<Document/06 - DRRAS_SRS.pdf>) describe the intended coursework scope.

Run `npm ci` and `npm run build` in `frontend/` to check the frontend. For hot reload with the Compose backend, open the frontend hot reload page in the [Docker guide](docs/DRRAS_docker.drawio).
