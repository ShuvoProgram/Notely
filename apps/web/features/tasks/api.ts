import { api } from "@/lib/api/client";
import type { CalendarStatus, Task, TaskCreateInput, TaskStatus } from "@/lib/api/types";

export const tasksApi = {
  list: (params: { status?: TaskStatus; note_id?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.note_id) qs.set("note_id", params.note_id);
    const s = qs.toString();
    return api.get<Task[]>(`/tasks${s ? `?${s}` : ""}`);
  },
  create: (input: TaskCreateInput) => api.post<Task>("/tasks", input),
  createMany: (tasks: TaskCreateInput[]) => api.post<Task[]>("/tasks/bulk", { tasks }),
  update: (id: string, input: Partial<TaskCreateInput> & { status?: TaskStatus; clear_due_date?: boolean; clear_due_time?: boolean }) =>
    api.patch<Task>(`/tasks/${id}`, input),
  remove: (id: string) => api.delete<{ deleted: boolean }>(`/tasks/${id}`),
  calendarStatus: () => api.get<CalendarStatus>("/tasks/calendar/status"),
  addToCalendar: (id: string) => api.post<Task>(`/tasks/${id}/calendar`, {}),
  removeFromCalendar: (id: string) => api.delete<Task>(`/tasks/${id}/calendar`),
};
