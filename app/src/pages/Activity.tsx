import { useQuery } from "@tanstack/react-query";
import { api, date } from "../lib/api";
import { Empty, ErrorNotice, Heading, Loading } from "../components/ui";
export function Activity() {
  const q = useQuery({
    queryKey: ["activity"],
    queryFn: () =>
      api<{ id: string; action: string; target: string; created_at: string }[]>(
        "/activity",
      ),
  });
  return (
    <div className="page">
      <Heading
        title="Your workspace, in motion."
        description="Recent actions recorded for your account."
      />
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorNotice error={q.error} />
      ) : !q.data?.length ? (
        <Empty title="A quiet workspace">
          Your repository and account activity will appear here.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Reference</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.action.replaceAll(".", " · ").replaceAll("_", " ")}
                  </td>
                  <td>
                    <code>{a.target.slice(0, 36)}</code>
                  </td>
                  <td>{date(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
