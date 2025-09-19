import { useState } from "react";
import axios from "axios";
import StudentTimetable from "./StudentTimeTable";

export default function StudentLookup() {
  const [studentId, setStudentId] = useState("");
  const [timetable, setTimetable] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSearch() {
    if (!studentId) {
      alert("Please enter a student ID");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.get(`http://localhost:5001/timetable/${studentId}`);
      setTimetable(res.data.timetable || []);
    } catch (err) {
      alert("Could not fetch timetable for this student.");
      setTimetable([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Enter Student ID"
          value={studentId}
          onChange={(e) => setStudentId(e.target.value)}
          className="border rounded-lg px-3 py-2 flex-1"
        />
        <button
          onClick={handleSearch}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg"
        >
          {loading ? "Loading..." : "Search"}
        </button>
      </div>

      {/* ✅ Properly closed JSX */}
      {timetable.length > 0 && (
        <StudentTimetable studentId={studentId} timetable={timetable} />
      )}
    </div>
  );
}
