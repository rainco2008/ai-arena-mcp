import { getTaskData } from "@/lib/data";
import { Status, short } from "../_components";

export const dynamic = "force-dynamic";

function taskHref(taskId: string) {
  return `/tasks?task_id=${encodeURIComponent(taskId)}`;
}

export default async function TasksPage({
  searchParams,
}: {
  searchParams?: Promise<{ task_id?: string }>;
}) {
  const params = await searchParams;
  const data = await getTaskData(params?.task_id);

  return (
    <section className="panel">
      <div className="panelHead">
        <div>
          <h1>Tasks</h1>
          <p className="panelSub">Submitted acquisition, processing, publishing, and metrics jobs.</p>
        </div>
      </div>

      {data.taskError ? (
        <section className="notice">
          <strong>Task table unavailable</strong>
          <span>{data.taskError}</span>
        </section>
      ) : null}

      <div className="gridTwo taskGrid">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Started</th>
                <th>Finished</th>
              </tr>
            </thead>
            <tbody>
              {data.tasks.map((task) => (
                <tr key={task.id} className={task.id === data.selectedTaskId ? "selectedRow" : undefined}>
                  <td>
                    <a href={taskHref(task.id)}>{short(task.taskType, 42)}</a>
                    <span className="rowHint">{short(task.id, 36)}</span>
                  </td>
                  <td><Status value={task.status} /></td>
                  <td>{task.progress}%</td>
                  <td>{short(task.startedAt || task.createdAt, 24)}</td>
                  <td>{short(task.finishedAt, 24)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <section className="taskLog">
          <h2>Logs</h2>
          {data.logs.length ? (
            data.logs.map((log) => (
              <pre key={log.id}><strong>{log.stream}</strong> {log.message}</pre>
            ))
          ) : (
            <p className="panelSub">No logs for the selected task.</p>
          )}
        </section>
      </div>
    </section>
  );
}
