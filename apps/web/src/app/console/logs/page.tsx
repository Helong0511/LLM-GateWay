import { redirect } from "next/navigation";

/** 用量与请求记录合并到同一页，避免客户找不到该看哪边。 */
export default function LogsPage() {
  redirect("/console/usage");
}
