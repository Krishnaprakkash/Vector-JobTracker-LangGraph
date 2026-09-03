// frontend/components/SearchBar.tsx
"use client";
import { useEffect, useState } from "react";
import { getMe, updateSearchQuery } from "@/lib/api";

export default function SearchBar({ onSearch }: { onSearch: (query: string) => void }) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    getMe().then((data) => {
      if (data.last_search_query) setQuery(data.last_search_query);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      await updateSearchQuery(query.trim());
    }
    onSearch(query.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. senior backend engineer"
        className="border rounded px-3 py-2 text-sm flex-1"
      />
      <button type="submit" className="px-4 py-2 bg-black text-white rounded text-sm">
        Search
      </button>
    </form>
  );
}