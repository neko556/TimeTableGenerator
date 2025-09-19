import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import GenerateButton from "./components/GenerateButton";
import StudentLookup from "./components/StudentLookup";
import MasterTimetable from "./components/MasterTimetable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";

function TypewriterHeading({ text, onDone }: { text: string; onDone: () => void }) {
  const [displayed, setDisplayed] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (index < text.length) {
      const timeout = setTimeout(() => {
        setDisplayed((prev) => prev + text[index]);
        setIndex(index + 1);
      }, 100);
      return () => clearTimeout(timeout);
    } else {
      onDone();
    }
  }, [index, text, onDone]);

  return (
    <motion.h1
      className="font-extrabold text-black"
      initial={{ fontSize: "4rem", y: 0 }}
      animate={{ fontSize: "2rem", y: -20 }}
      transition={{ delay: 2, duration: 1 }}
    >
      {displayed}
      <span className="animate-pulse">|</span>
    </motion.h1>
  );
}

function App() {
  const [showButton, setShowButton] = useState(false);
  const [generated, setGenerated] = useState(false);

  return (
    <div
      className="min-h-screen flex flex-col items-center bg-cover bg-center relative"
      style={{ backgroundImage: "url('/bg.png')" }}
    >
      <AnimatePresence mode="wait">
        {!generated ? (
          // ===== Stage 1: Landing =====
          <motion.div
            key="landing"
            className="flex flex-col items-center justify-center min-h-screen space-y-8 w-full bg-white/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -50 }}
            transition={{ duration: 0.8 }}
          >
            <TypewriterHeading
              text="AI Timetable Generator"
              onDone={() => setShowButton(true)}
            />
            {showButton && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 1 }}
              >
                <GenerateButton onGenerated={() => setGenerated(true)} />
              </motion.div>
            )}
          </motion.div>
        ) : (
          // ===== Stage 2: Dashboard =====
          <motion.div
            key="dashboard"
            className="absolute inset-0 bg-white/40 backdrop-blur-md flex flex-col"
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.8 }}
          >
            {/* Compact heading at top */}
            <header className="w-full py-4 text-center bg-white/60 shadow">
              <h1 className="text-2xl font-bold text-black">
                AI Timetable Generator
              </h1>
            </header>

            {/* Tabs */}
            <main className="flex-1 p-6">
              <Tabs defaultValue="student" className="w-full">
                <TabsList className="flex justify-center space-x-4 bg-gray-100 rounded-lg p-2">
                  <TabsTrigger value="student">Student Timetable</TabsTrigger>
                  <TabsTrigger value="master">Master Timetable</TabsTrigger>
                  <TabsTrigger value="faculty">Faculty Timetable</TabsTrigger>
                </TabsList>

                <TabsContent value="student" className="mt-6">
                  <StudentLookup />
                </TabsContent>

                <TabsContent value="master" className="mt-6">
                  <MasterTimetable />
                </TabsContent>

                <TabsContent
                  value="faculty"
                  className="mt-6 text-center text-gray-500"
                >
                  🚧 Faculty timetable coming soon...
                </TabsContent>
              </Tabs>
            </main>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default App;
