import { Alert, Button } from "antd";

export function InlineError({ error, title = "Unable to load this section", onRetry }: {
  error: Error | string;
  title?: string;
  onRetry?: () => void;
}) {
  return (
    <Alert
      showIcon
      type="error"
      message={title}
      description={error instanceof Error ? error.message : error}
      action={onRetry ? <Button size="small" danger onClick={onRetry}>Retry</Button> : undefined}
    />
  );
}
