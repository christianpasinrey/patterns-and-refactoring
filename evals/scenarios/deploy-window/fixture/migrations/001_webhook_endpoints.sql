CREATE TABLE webhook_endpoints (
    id bigserial PRIMARY KEY,
    url text NOT NULL,
    signing_secret text NOT NULL,
    failures integer NOT NULL DEFAULT 0,
    paused boolean NOT NULL DEFAULT false
);
