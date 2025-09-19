import { useState } from "react";
import axios from "axios";

type TimetableEntry = {
  "Batch/Group ID": string;
  "Course ID": string;
  "Day": string;
  "Faculty ID": string;
  "Room ID": string;
  "Time": string;
  "Time Slot"?: string; // sometimes backend may send both
};

// helper to convert "HH:MM-HH:MM" to minutes
function toMinutes(slot: string) {
  if (!slot) return 0;
  const match = slot.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return 0;
  const [, h, m] = match;
  return parseInt(h) * 60 + parseInt(m);
}

// fix day ordering (not alphabetical)
const dayOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export default function MasterTimetable() {
  const [records, setRecords] = useState<TimetableEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchMaster() {
    setLoading(true);
    setError("");
    try {
      const res = await axios.get("http://localhost:5001/master");
      setRecords(res.data.master_timetable || []);
    } catch (err) {
      setError("Failed to fetch master timetable. Did you run /generate?");
    } finally {
      setLoading(false);
    }
  }

  // group records by section
  const grouped: Record<string, TimetableEntry[]> = {};
  records.forEach((rec) => {
    const section = rec["Batch/Group ID"] || "Unknown";
    if (!grouped[section]) grouped[section] = [];
    grouped[section].push(rec);
  });

  return (
    <div className="space-y-6">
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

      {/* Render one table per section */}
      {Object.entries(grouped).map(([section, entries]) => {
        const days = Array.from(new Set(entries.map((t) => t.Day))).sort(
          (a, b) => dayOrder.indexOf(a) - dayOrder.indexOf(b)
        );

        const timeSlots = Array.from(
          new Set(entries.map((t) => t["Time"] || t["Time Slot"] || ""))
        )
          .filter(Boolean) // remove empty strings
          .sort((a, b) => toMinutes(a) - toMinutes(b));

        // build grid day → time → entry
        const grid: Record<string, Record<string, TimetableEntry | null>> = {};
        days.forEach((d) => {
          grid[d] = {};
          timeSlots.forEach((slot) => (grid[d][slot] = null));
        });
        entries.forEach((e) => {
          const slot = e["Time"] || e["Time Slot"];
          if (slot) {
            grid[e.Day][slot] = e;
          }
        });

        return (
          <div key={section} className="space-y-2">
            <h2 className="text-lg font-bold text-purple-700">
              📌 Section: {section}
            </h2>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse border text-sm text-center">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="border px-3 py-2">Day</th>
                    {timeSlots.map((slot) => (
                      <th key={slot} className="border px-3 py-2">
                        {slot}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {days.map((day) => (
                    <tr key={day}>
                      <td className="border px-3 py-2 font-semibold bg-gray-50">
                        {day}
                      </td>
                      {timeSlots.map((slot) => {
                        const entry = grid[day][slot];
                        return (
                          <td
                            key={slot}
                            className="border px-3 py-2 align-top hover:bg-gray-50"
                          >
                            {entry ? (
                              <div className="space-y-1">
                                <div className="font-medium">{entry["Course ID"]}</div>
                                <div className="text-xs text-gray-600">
                                  {entry["Faculty ID"]}
                                </div>
                                <div className="text-xs text-gray-500">
                                  {entry["Room ID"]}
                                </div>
                              </div>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
