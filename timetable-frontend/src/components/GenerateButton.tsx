import { useState } from "react";
import axios from "axios";

export default function GenerateButton({ onGenerated }: { onGenerated: () => void }) {
  const [loading, setLoading] = useState(false);

  async function handleGenerate() {
    if (loading) return;

    // optional: confirm re-run
    if (window.confirm("Do you want to regenerate the timetable? This may take time.")) {
      setLoading(true);
      try {
        const res = await axios.get("http://localhost:5000/generate");
        alert(res.data.message || "Timetable generated!");
        onGenerated();
      } catch (err) {
        alert("Failed to generate timetable.");
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <button
      onClick={handleGenerate}
      disabled={loading}
      className={`px-4 py-2 rounded-lg text-white ${
        loading ? "bg-gray-500 cursor-not-allowed" : "bg-green-600"
      }`}
    >
      {loading ? "Generating..." : "Generate Timetable"}
    </button>
  );
}
