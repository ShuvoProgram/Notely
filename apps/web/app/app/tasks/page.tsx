import type { Metadata } from "next";

import { TaskList } from "@/features/tasks/components/task-list";

export const metadata: Metadata = { title: "Tasks" };

export default function TasksPage() {
  return <TaskList />;
}
