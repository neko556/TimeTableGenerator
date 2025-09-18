import { useState } from "react";
import GenerateButton from "./components/GenerateButton";
import StudentLookup from "./components/StudentLookup";
import MasterTimetable from "./components/MasterTimetable";

function App() {
  const [generated, setGenerated] = useState(false);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Automatic Timetable Generator</h1>

      {/* Generate once */}
      <GenerateButton onGenerated={() => setGenerated(true)} />

      {/* Show only after generated */}
      {generated && (
        <>
          <h2 className="text-xl font-semibold">Student Timetable</h2>
          <StudentLookup />

          <h2 className="text-xl font-semibold">Master Timetable</h2>
          <MasterTimetable />
        </>
      )}
    </div>
  );
}

export default App;
