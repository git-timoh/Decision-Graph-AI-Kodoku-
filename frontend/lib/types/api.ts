import type { components, paths } from "@/lib/types/contracts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type SessionCreate = components["schemas"]["SessionCreate"];
export type SessionCreateResponse = components["schemas"]["SessionCreateResponse"];
export type SessionResponse = components["schemas"]["SessionResponse"];
export type SessionListItem = components["schemas"]["SessionListItem"];
export type SessionDetailResponse = components["schemas"]["SessionDetailResponse"];
export type SessionUpdate = components["schemas"]["SessionUpdate"];
export type SessionConfig = components["schemas"]["SessionConfig"];
export type NodeDTO = components["schemas"]["NodeDTO"];
export type EvaluationDTO = components["schemas"]["EvaluationDTO"];
export type CheckpointDTO = components["schemas"]["CheckpointDTO"];
export type ProviderStatus = components["schemas"]["ProviderStatus"];
export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type SettingsUpdate = components["schemas"]["SettingsUpdate"];
export type SettingsTestResponse = components["schemas"]["SettingsTestResponse"];

export type ListSessionsPath = paths["/sessions"]["get"];
export type CreateSessionPath = paths["/sessions"]["post"];
export type GetSessionPath = paths["/sessions/{session_id}"]["get"];
