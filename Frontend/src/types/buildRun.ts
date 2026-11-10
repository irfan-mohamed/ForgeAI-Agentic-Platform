export interface TestSuite {
  name: string;
  passed: number;
  failed: number;
  errors: number;
  duration: number;
}

export interface TestResults {
  passed: number;
  failed: number;
  errors: number;
  duration: number;
  exit_code: number;
  suites: TestSuite[];
  raw_output?: string;
}

export interface Patch {
  task_id: string;
  file_path: string;
  diff: string;
}

export type BuildRunStatus =
  | 'queued'
  | 'building'
  | 'integration_testing'
  | 'pr_opened'
  | 'failed';

export interface BuildRunOut {
  id: string;
  plan_id: string;
  organization_id: number;
  repository_id: number;
  triggered_by_user_id: number;
  status: BuildRunStatus;
  build_log: string | null;
  otel_trace_id: string | null;
  test_results: TestResults | null;
  generated_patches: Patch[] | null;
  pull_request_url: string | null;
  pull_request_number: number | null;
  branch_name: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
