# Studio architecture

Studio presents the system model and checked stories. Navigation, map and story components use the
state, model, API and DOM components. The presentation components call each other. The core decides
architecture rules and verdicts.

The Studio server has no current schema for its query endpoints. The system contract does not declare
an interface for them until a schema describes the actual messages.
