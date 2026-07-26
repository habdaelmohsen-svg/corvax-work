export type CorvaxAiMode = 'help' | 'data' | 'analysis';
export type CorvaxAiRole = 'user' | 'assistant' | 'system';
export type CorvaxAiConfidence = 'high' | 'medium' | 'low';

export type CorvaxAiSourceType =
  | 'system-guide'
  | 'policy'
  | 'screen-context'
  | 'report'
  | 'transaction'
  | 'knowledge-base'
  | 'database';

export interface CorvaxAiSource {
  id: string;
  title: string;
  type: CorvaxAiSourceType;
  reference?: string;
  updatedAt?: string;
}

export interface CorvaxAiMessage {
  id: string;
  role: CorvaxAiRole;
  text: string;
  createdAt?: string;
  sources?: CorvaxAiSource[];
  confidence?: CorvaxAiConfidence;
  limitation?: string;
}

export interface CorvaxAiScreenContext {
  companyId: number;
  companyName: string;
  branchId?: number;
  branchName?: string;
  module: string;
  screen: string;
  documentReference?: string;
  locale: 'ar' | 'en';
  readOnly: true;
}

export interface CorvaxAiAssistantProps {
  open: boolean;
  mode: CorvaxAiMode;
  context: CorvaxAiScreenContext;
  messages: CorvaxAiMessage[];
  busy?: boolean;
  onOpenChange: (open: boolean) => void;
  onModeChange: (mode: CorvaxAiMode) => void;
  onSend: (message: string) => void;
}

export interface CorvaxAiApiSource {
  type: CorvaxAiSourceType;
  reference: string;
  title: string;
  updated_at?: string | null;
}

export interface CorvaxAiApiResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  confidence: CorvaxAiConfidence;
  limitations: string[];
  sources: CorvaxAiApiSource[];
  tool_trace_id: string;
}
