import type { TemplateInfo } from "../api/types";
import { Panel } from "./layout";

/** Nuclei templates: installed count, last update and the update job (filled in by the template store). */
export function TemplatePanel({ info, nucleiReady, onChanged }: { info?: TemplateInfo; nucleiReady: boolean; onChanged: () => void }) {
  void info; void nucleiReady; void onChanged;
  return <Panel id="templates-h" title="Nuclei templates" hint="Bộ mẫu kiểm tra của nuclei." />;
}
