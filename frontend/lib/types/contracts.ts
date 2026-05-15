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
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
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
}
