"use client";
import { useEffect, useState } from "react";
import { getMe, updateSearchQuery, updateHomeLocation } from "@/lib/api";

const COUNTRIES = [
  "", "United States", "India", "United Kingdom", "Canada", "Germany", "France",
  "Singapore", "Australia", "Japan", "Netherlands", "Ireland", "Spain", "Italy",
  "Poland", "Mexico", "Brazil", "Remote",
];

export default function SearchBar({ onSearch }: { onSearch: (query: string) => void }) {
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");

  useEffect(() => {
    getMe().then((data) => {
      if (data.last_search_query) setQuery(data.last_search_query);
      if (data.home_location) setLocation(data.home_location);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      await updateSearchQuery(query.trim());
    }
    await updateHomeLocation(location);
    onSearch(query.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. Software Engineer, Agentic AI, MERN"
        className="border rounded px-3 py-2 text-sm flex-1"
      />
      <select
        value={location}
        onChange={(e) => setLocation(e.target.value)}
        className="border rounded px-3 py-2 text-sm"
      >
        <option value="">Any location</option>
        {COUNTRIES.filter(Boolean).map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      <button type="submit" className="px-4 py-2 bg-black text-white rounded text-sm">
        Search
      </button>
    </form>
  );
}