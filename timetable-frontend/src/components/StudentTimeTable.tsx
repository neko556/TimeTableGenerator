type TimetableEntry = {
  "Batch/Group ID": string;
  "Course ID": string;
  "Day": string;
  "Faculty ID": string;
  "Room ID": string;
  "Time": string;
  "Time Slot": string;
};

export default function StudentTimetable({ studentId, timetable }: { studentId: string, timetable: TimetableEntry[] }) {
  if (!timetable || timetable.length === 0) {
    return <p className="text-gray-600">No classes found for student {studentId}.</p>;
  }

  // group by day
  const grouped: Record<string, TimetableEntry[]> = {};
  timetable.forEach((entry) => {
    if (!grouped[entry.Day]) grouped[entry.Day] = [];
    grouped[entry.Day].push(entry);
  });

  // sort by time
  Object.keys(grouped).forEach((day) => {
    grouped[day] = grouped[day].sort((a, b) => a.Time.localeCompare(b.Time));
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">📅 Timetable for {studentId}</h2>

      {Object.keys(grouped).map((day) => (
        <div key={day} className="border rounded-lg shadow-md p-4">
          <h3 className="text-lg font-semibold mb-2">{day}</h3>
          <table className="w-full border-collapse border text-sm">
            <thead className="bg-gray-100">
              <tr>
                <th className="border px-3 py-2">Time</th>
                <th className="border px-3 py-2">Course</th>
                <th className="border px-3 py-2">Faculty</th>
                <th className="border px-3 py-2">Room</th>
                <th className="border px-3 py-2">Batch/Group</th>
              </tr>
            </thead>
            <tbody>
              {grouped[day].map((entry, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="border px-3 py-2">{entry.Time}</td>
                  <td className="border px-3 py-2">{entry["Course ID"]}</td>
                  <td className="border px-3 py-2">{entry["Faculty ID"]}</td>
                  <td className="border px-3 py-2">{entry["Room ID"]}</td>
                  <td className="border px-3 py-2">{entry["Batch/Group ID"]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
