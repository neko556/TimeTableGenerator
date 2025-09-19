type TimetableEntry = {
  "Batch/Group ID": string;
  "Course ID": string;
  "Day": string;
  "Faculty ID": string;
  "Room ID": string;
  "Time": string;
  "Time Slot": string;
};

export default function StudentTimetable({
  studentId,
  timetable,
}: {
  studentId: string;
  timetable: TimetableEntry[];
}) {
  if (!timetable || timetable.length === 0) {
    return (
      <p className="text-gray-600">
        No classes found for student {studentId}.
      </p>
    );
  }

  // Unique sorted days & time slots
  const days = Array.from(new Set(timetable.map((t) => t.Day)));
  const timeSlots = Array.from(new Set(timetable.map((t) => t["Time Slot"]))).sort();

  // Map (day, time slot) -> entry
  const grid: Record<string, Record<string, TimetableEntry | null>> = {};
  days.forEach((day) => {
    grid[day] = {};
    timeSlots.forEach((slot) => {
      grid[day][slot] = null;
    });
  });

  timetable.forEach((entry) => {
    grid[entry.Day][entry["Time Slot"]] = entry;
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">📅 Timetable for {studentId}</h2>

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
}
