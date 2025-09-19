import { useState } from "react";
import axios from "axios";

export default function MasterTimetable() {
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchMaster() {
    setLoading(true);
    setError("");
    try {
      const res = await axios.get("http://localhost:5000/master");
      setRecords(res.data.master_timetable || []);
    } catch (err) {
      setError("Failed to fetch master timetable. Did you run /generate?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <button
        onClick={fetchMaster}
        disabled={loading}
        className="bg-purple-600 text-white px-4 py-2 rounded-lg disabled:opacity-50"
      >
        {loading ? "Loading..." : "Load Master Timetable"}
      </button>

      {error && <div className="text-red-600">{error}</div>}

      {!loading && records.length === 0 && !error && (
        <div className="text-gray-500">No timetable loaded yet.</div>
      )}

      {records.length > 0 && (
        <table className="w-full border-collapse border text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="border px-3 py-2">Day</th>
              <th className="border px-3 py-2">Time</th>
              <th className="border px-3 py-2">Course</th>
              <th className="border px-3 py-2">Faculty</th>
              <th className="border px-3 py-2">Room</th>
              <th className="border px-3 py-2">Batch/Group</th>
            </tr>
          </thead>
          <tbody>
            {records.map((row, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="border px-3 py-2">{row.Day}</td>
                <td className="border px-3 py-2">{row.Time}</td>
                <td className="border px-3 py-2">{row["Course ID"]}</td>
                <td className="border px-3 py-2">{row["Faculty ID"]}</td>
                <td className="border px-3 py-2">{row["Room ID"]}</td>
                <td className="border px-3 py-2">{row["Batch/Group ID"]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
