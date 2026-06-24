/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Regenerate with: `npm run gen:contracts` (backend must be running on
 * ${KODOKU_BACKEND_URL:-http://localhost:8000}).
 */
/* eslint-disable */

export interface paths {
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Healthz */
        get: operations["healthz_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Sessions */
        get: operations["list_sessions_sessions_get"];
        put?: never;
        /** Create Session */
        post: operations["create_session_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Session */
        get: operations["get_session_sessions__session_id__get"];
        put?: never;
        post?: never;
        /** Delete Session */
        delete: operations["delete_session_sessions__session_id__delete"];
        options?: never;
        head?: never;
        /** Update Session */
        patch: operations["update_session_sessions__session_id__patch"];
        trace?: never;
    };
    "/sessions/{session_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Replay Events */
        get: operations["replay_events_sessions__session_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/debug/emit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Debug Emit
         * @description Emit a scripted storyline to drive frontend development.
         */
        post: operations["debug_emit_sessions__session_id__debug_emit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Run */
        post: operations["start_run_sessions__session_id__run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume Run */
        post: operations["resume_run_sessions__session_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/interrupt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Interrupt Run */
        post: operations["interrupt_run_sessions__session_id__interrupt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Settings */
        get: operations["read_settings_settings_get"];
        /** Update Settings */
        put: operations["update_settings_settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/settings/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Test Settings
         * @description Connection check: one tiny completion on the `evaluate` role client.
         *
         *     Never raises — any failure (bad key, unreachable provider, etc.) is
         *     reported as `{ok: false, error: <message>}` rather than propagated, since
         *     this is a smoke check, not a critical endpoint. The error message comes
         *     from the provider's exception only; no stored key is ever included.
         */
        post: operations["test_settings_settings_test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** CheckpointDTO */
        CheckpointDTO: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            kind: components["schemas"]["CheckpointKind"];
            /** Payload */
            payload: Record<string, never>;
            /** Decision */
            decision: Record<string, never> | null;
            /** Resolved At */
            resolved_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * CheckpointKind
         * @enum {string}
         */
        CheckpointKind: "post_expand" | "post_evaluate" | "pre_synthesis";
        /** DebugEmitResponse */
        DebugEmitResponse: {
            /** Emitted */
            emitted: number;
            /** Last Event Id */
            last_event_id: number;
        };
        /** EvaluationDTO */
        EvaluationDTO: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Node Id
             * Format: uuid
             */
            node_id: string;
            /** Score */
            score: string;
            /** Critique */
            critique: string;
            /** Dimensions */
            dimensions: Record<string, never>;
            /** Model */
            model: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
            /** Version */
            version: string;
        };
        /** InterruptResponse */
        InterruptResponse: {
            /** Interrupted */
            interrupted: boolean;
        };
        /** NodeDTO */
        NodeDTO: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Depth */
            depth: number;
            kind: components["schemas"]["NodeKind"];
            /** Title */
            title: string;
            /** Content */
            content: string;
            status: components["schemas"]["NodeStatus"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** NodeEdit */
        NodeEdit: {
            /** Title */
            title?: string | null;
            /** Content */
            content?: string | null;
        };
        /**
         * NodeKind
         * @enum {string}
         */
        NodeKind: "root" | "candidate" | "synthesis";
        /**
         * NodeStatus
         * @enum {string}
         */
        NodeStatus: "pending" | "active" | "pruned" | "kept" | "expanded";
        /** ProviderStatus */
        ProviderStatus: {
            /** Set */
            set: boolean;
            /** Hint */
            hint?: string | null;
        };
        /**
         * ResumeRequest
         * @description Body of `POST /sessions/{id}/resume`.
         *
         *     `keep ∪ prune` must be a subset of the resolved checkpoint's candidate
         *     node ids — that check happens in the endpoint, where the checkpoint (and
         *     therefore its candidate ids) is loaded; the DTO has no DB access so it
         *     can't validate it itself.
         */
        ResumeRequest: {
            /**
             * Checkpoint Id
             * Format: uuid
             */
            checkpoint_id: string;
            /** Keep */
            keep?: string[];
            /** Prune */
            prune?: string[];
            /** Edits */
            edits?: {
                [key: string]: components["schemas"]["NodeEdit"];
            };
        };
        /** ResumeResponse */
        ResumeResponse: {
            /** Status */
            status: string;
        };
        /** RunResponse */
        RunResponse: {
            /** Status */
            status: string;
        };
        /** SessionConfig */
        SessionConfig: {
            /**
             * Model
             * @default anthropic/claude-sonnet-4-6
             */
            model: string;
            /**
             * Branching Factor
             * @default 3
             */
            branching_factor: number;
            /**
             * Max Depth
             * @default 3
             */
            max_depth: number;
            /**
             * Temperature
             * @default 0.7
             */
            temperature: number;
            /**
             * Hitl Mode
             * @default autopilot
             * @enum {string}
             */
            hitl_mode: "autopilot" | "every_branch";
            /**
             * Decide Mode
             * @default threshold
             * @enum {string}
             */
            decide_mode: "threshold" | "judge";
            /** Budget Usd */
            budget_usd?: number | null;
            /** Branch Models */
            branch_models?: string[] | null;
        };
        /** SessionCreate */
        SessionCreate: {
            /** Goal */
            goal: string;
            /** Title */
            title?: string | null;
            config?: components["schemas"]["SessionConfig"] | null;
        };
        /** SessionCreateResponse */
        SessionCreateResponse: {
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
        };
        /** SessionDetailResponse */
        SessionDetailResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** User Id */
            user_id: string;
            /** Title */
            title: string;
            /** Goal */
            goal: string;
            status: components["schemas"]["SessionStatus"];
            /** Config */
            config: Record<string, never>;
            /** Current Step */
            current_step: string | null;
            /** Final Synthesis */
            final_synthesis: string | null;
            /** Cost Usd */
            cost_usd: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Nodes */
            nodes: components["schemas"]["NodeDTO"][];
            /** Evaluations */
            evaluations: components["schemas"]["EvaluationDTO"][];
            /** Checkpoints */
            checkpoints: components["schemas"]["CheckpointDTO"][];
        };
        /** SessionListItem */
        SessionListItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            status: components["schemas"]["SessionStatus"];
            /** Current Step */
            current_step: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** SessionResponse */
        SessionResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** User Id */
            user_id: string;
            /** Title */
            title: string;
            /** Goal */
            goal: string;
            status: components["schemas"]["SessionStatus"];
            /** Config */
            config: Record<string, never>;
            /** Current Step */
            current_step: string | null;
            /** Final Synthesis */
            final_synthesis: string | null;
            /** Cost Usd */
            cost_usd: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * SessionStatus
         * @enum {string}
         */
        SessionStatus: "draft" | "running" | "awaiting_human" | "done" | "error" | "paused";
        /** SessionUpdate */
        SessionUpdate: {
            /** Title */
            title?: string | null;
            config?: components["schemas"]["SessionConfig"] | null;
        };
        /** SettingsResponse */
        SettingsResponse: {
            /** Providers */
            providers: {
                [key: string]: components["schemas"]["ProviderStatus"];
            };
            /** Ollama Base Url */
            ollama_base_url?: string | null;
            /** Models */
            models: {
                [key: string]: string | null;
            };
        };
        /** SettingsTestResponse */
        SettingsTestResponse: {
            /** Ok */
            ok: boolean;
            /** Error */
            error?: string | null;
        };
        /** SettingsUpdate */
        SettingsUpdate: {
            /** Providers */
            providers?: {
                [key: string]: string | null;
            } | null;
            /** Ollama Base Url */
            ollama_base_url?: string | null;
            /** Models */
            models?: {
                [key: string]: string;
            } | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WsEvent
         * @description A single server-push message; mirrors a row in the `events` journal.
         */
        WsEvent: {
            /** Id */
            id: number;
            /** Type */
            type: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /**
             * Ts
             * Format: date-time
             */
            ts: string;
            /** Payload */
            payload: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    healthz_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    list_sessions_sessions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionListItem"][];
                };
            };
        };
    };
    create_session_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_session_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_session_sessions__session_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_session_sessions__session_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replay_events_sessions__session_id__events_get: {
        parameters: {
            query?: {
                since?: number;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WsEvent"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    debug_emit_sessions__session_id__debug_emit_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DebugEmitResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_run_sessions__session_id__run_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_run_sessions__session_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResumeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    interrupt_run_sessions__session_id__interrupt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InterruptResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_settings_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsResponse"];
                };
            };
        };
    };
    update_settings_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingsUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_settings_settings_test_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsTestResponse"];
                };
            };
        };
    };
}
