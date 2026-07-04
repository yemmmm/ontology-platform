import { Alert, Button } from "antd";
import { useT } from "../../i18n";

export function InlineError({ error, title, onRetry }: {
  error: Error | string;
  title?: string;
  onRetry?: () => void;
}) {
  const t = useT();
  return (
    <Alert
      showIcon
      type="error"
      message={title ? t(title) : t("Unable to load this section")}
      description={error instanceof Error ? error.message : error}
      action={onRetry ? <Button size="small" danger onClick={onRetry}>{t("Retry")}</Button> : undefined}
    />
  );
}
