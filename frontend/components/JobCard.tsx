type Job = {
  id: string;
  company: string;
  title: string;
  url: string | null;
  location: string | null;
  source: string;
  match_score: number | null;
  match_rationale: string | null;
  comp_min: number | null;
  comp_max: number | null;
  comp_currency: string | null;
  comp_estimated: boolean;
  status: string;
};

export default function JobCard({ job }: { job: Job }) {
  const comp =
    job.comp_min && job.comp_max
      ? `${job.comp_currency ?? "USD"} ${job.comp_min.toLocaleString()}–${job.comp_max.toLocaleString()}${job.comp_estimated ? " (est.)" : ""}`
      : null;

  return (
    <div className="border rounded-lg p-4 flex flex-col gap-2 bg-white shadow-sm">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold text-sm">{job.title}</h3>
          <p className="text-xs text-gray-500">{job.company} · {job.location ?? "—"}</p>
        </div>
        <span className="text-[10px] uppercase text-gray-400">{job.source}</span>
      </div>

      {job.match_score !== null && (
        <div className="text-xs">
          <span className="font-medium">Fit: {Math.round(job.match_score)}</span>
        </div>
      )}
      {job.match_rationale && <p className="text-xs text-gray-600">{job.match_rationale}</p>}

      {comp && <p className="text-xs text-gray-700">{comp}</p>}

      {job.url && (
        <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 underline mt-auto">
          View job
        </a>
      )}
    </div>
  );
}