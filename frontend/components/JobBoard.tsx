"use client";
import { useEffect, useState } from "react";
import { clearJobs, getTaskStatus, getJobs } from "@/lib/api";
import JobCard from "./JobCard";
import SearchBar from "./SearchBar";

type Job = Parameters<typeof JobCard>[0]["job"];

export default function JobBoard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const loadJobs = async () => {
    const data = await getJobs();
    setJobs(data);
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const pollTask = async (taskId: string) => {
    const poll = async () => {
      const status = await getTaskStatus(taskId);
      if (status.status === "done") {
        setLoading(false);
        setStatusMsg(`Inserted ${status.detail.inserted ?? 0}, scored ${status.detail.scored ?? 0}`);
        await loadJobs();
        return;
      }
      if (status.status === "failed") {
        setLoading(false);
        setStatusMsg(`Error: ${status.detail.error ?? "unknown"}`);
        return;
      }
      setTimeout(poll, 2000);
    };
    poll();
  };

  const handleRefresh = async () => {
    setLoading(true);
    setStatusMsg("Refreshing...");
    const { task_id } = await clearJobs();
    pollTask(task_id);
  };

  return (
    <div className="p-6">
      <SearchBar onSearch={handleRefresh} />

      <div className="flex gap-3 mb-4 items-center">
        <button onClick={handleRefresh} disabled={loading} className="px-4 py-2 bg-black text-white rounded disabled:opacity-50 flex items-center gap-2">
          {loading && (
            <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          )}
          {loading ? "Refreshing..." : "Refresh"}
        </button>
        {statusMsg && !loading && <span className="text-sm text-gray-500">{statusMsg}</span>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
}