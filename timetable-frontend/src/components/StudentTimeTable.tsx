// timetable-frontend/src/components/StudentTimeTable.tsx
import React from "react";

type TimetableEntry = {
  "Batch/Group ID"?: string;
  "Course ID"?: string;
  "Day": string;
  "Faculty ID"?: string;
  "Room ID"?: string;
  "Time"?: string;
  "Time Slot"?: string;
};

const DAY_ORDER = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function toMinutes(slot: string) {
  if (!slot) return 0;
  const sep = slot.includes("-") ? "-" : slot.includes("–") ? "–" : "-";
  const start = slot.split(sep)[0].trim();
  const match = start.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return 0;
  const [, hh, mm] = match;
  return parseInt(hh, 10) * 60 + parseInt(mm, 10);
}

function sanitizeSlot(raw: string | undefined) {
  if (!raw) return "";
  const parts = raw.split("_");
  if (parts.length >= 2 && DAY_ORDER.includes(parts[0])) {
    return parts.slice(1).join("_");
  }
  return raw;
}

export default function StudentTimetable({
  studentId,
  timetable,
}: {
  studentId: string;
  timetable: TimetableEntry[];
}) {
  if (!timetable || timetable.length === 0) {
    return (
      <p className="text-gray-600 text-center py-6">
        No classes found for student <span className="font-semibold">{studentId}</span>.
      </p>
    );
  }

  const timeSlotsSet = new Set<string>();
  timetable.forEach((t) => {
    const s = sanitizeSlot(t["Time Slot"] ?? t["Time"]);
    if (s) timeSlotsSet.add(s);
  });

  const timeSlots = Array.from(timeSlotsSet).sort((a, b) => toMinutes(a) - toMinutes(b));

  if (timeSlots.length === 0) {
    return (
      <p className="text-gray-600 text-center py-6">
        No time slots available in the timetable data for {studentId}.
      </p>
    );
  }

  const grid: Record<string, Record<string, TimetableEntry | null>> = {};
  timeSlots.forEach((slot) => {
    grid[slot] = {};
    DAY_ORDER.forEach((d) => {
      grid[slot][d] = null;
    });
  });

  timetable.forEach((entry) => {
    const slot = sanitizeSlot(entry["Time Slot"] ?? entry["Time"]);
    if (!slot) return;
    const day = entry.Day;
    if (!DAY_ORDER.includes(day)) return;
    grid[slot][day] = entry;
  });

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-center">
        📅 Timetable for <span className="text-blue-600">{studentId}</span>
      </h2>

      <div className="overflow-x-auto rounded-lg shadow-lg">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-gradient-to-r from-blue-500 to-indigo-600 text-white sticky top-0">
            <tr>
              <th className="px-4 py-3 text-left">Day</th>
              {timeSlots.map((slot) => (
                <th
                  key={slot}
                  className="px-4 py-3 text-center whitespace-nowrap"
                >
                  {slot}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="bg-white">
            {DAY_ORDER.map((day) => (
              <tr
                key={day}
                className="hover:bg-gray-50 transition-colors duration-200"
              >
                <td className="px-4 py-3 font-semibold text-gray-700 bg-gray-50 sticky left-0">
                  {day}
                </td>

                {timeSlots.map((slot) => {
                  const entry = grid[slot][day];
                  return (
                    <td
                      key={day + "|" + slot}
                      className="px-3 py-3 text-center"
                    >
                      {entry ? (
                        <div className="p-2 rounded-lg shadow-sm bg-blue-50 border border-blue-100 hover:bg-blue-100 transition">
                          <div className="font-medium text-blue-700">
                            {entry["Course ID"]}
                          </div>
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
