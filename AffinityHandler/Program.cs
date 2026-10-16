// affinity-on-linux.exe -- open documents in Affinity from a Linux file manager.
//
// SOURCE OF TRUTH: this file is developed in a separate repository, next to the
// Wine patches it depends on; the copy in AffinityHandler/ is what the installer
// ships and is synced from there. Keep the two identical: they drifted once, by
// 511 lines, and the shipped copy kept a watchdog that killed live sessions.
//
// Replaces the affinity-open shell script. Set it as the .desktop Exec target:
//
//     Exec=<wine> "C:\Program Files\Affinity\Affinity\affinity-on-linux.exe" %F
//
// It runs inside the prefix, so it needs no external tools -- no wmctrl, no
// xdotool, no /proc scanning, and no shell quoting to get wrong.
//
// WHAT IT DOES
//
//   * converts the Unix paths the file manager hands it into DOS paths
//     (kernel32!wine_get_dos_file_name -- Wine converts argv[0] but passes
//     arguments through verbatim, so this is genuinely required)
//   * serialises concurrent double-clicks on a named mutex, so two fast clicks
//     cannot both decide "not running" and both cold start
//   * warm (an instance is up): hands each document straight to Affinity.exe
//     and lets Affinity's own single-instance handoff forward it
//   * cold: goes through AffinityHook.exe when it is installed, so plugins load,
//     and watches for the intermittent startup deadlock
//   * clears a shutdown zombie first -- an Affinity 3.3 that logged "Exit" and
//     then deadlocked in libnetwork.dll's process detach. See THE SHUTDOWN
//     ZOMBIE below; it is why a launch can appear to do nothing at all.
//
// It also answers two subcommands, for when you want the reaper without a
// launch:
//
//     affinity-on-linux.exe --reap            clear a spent leftover now
//     affinity-on-linux.exe --reap-dry-run    say what that would do, kill nothing
//
// WHY WARM SKIPS AffinityHook.exe
//
// AffinityHook's job is to inject AffinityPluginLoader.dll into the process it
// starts. On a warm handoff that process forwards the document to the running
// instance and exits in about a second, so injecting into it achieves nothing.
// Skipping it is a second faster and -- because the hook forwards its arguments
// with string.Join(" ", args) and no quoting -- avoids splitting any path that
// contains a space. See TWO-STAGE COLD START below for the cold equivalent.
//
// WHY IT DOES NOT RAISE THE WINDOW
//
// It used to have to. Affinity's own SetForegroundWindow was failing, so the
// script called `wmctrl -i -a`. The wineserver was denying the request -- to
// every Wine process, including Affinity raising its own window -- whenever the
// X focus sat on a window that does not belong to Wine. Fixed by
// patches/wine/0019; see docs/wine-bug-foreground-denied.md. THIS PROGRAM
// REQUIRES THAT PATCH. Without it the document still opens, but the window
// stays behind whatever the file manager is.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace AffinityOnLinux
{
    internal static class Program
    {
        private const string MutexName = "Global\\AffinityOnLinux.launch";
        private const int StallSeconds = 45;   // matches affinity-launch
        private const int MaxTries = 3;

        private static StreamWriter _log;

        private static int Main(string[] args)
        {
            OpenLog();
            Log("invoked: " + string.Join(" | ", args));

            // Serialise. Two quick double-clicks used to both see "not running"
            // and both cold start.
            using (var mutex = new Mutex(false, MutexName))
            {
                bool held = false;
                try
                {
                    try { held = mutex.WaitOne(TimeSpan.FromSeconds(90)); }
                    catch (AbandonedMutexException) { held = true; }
                    return Run(args);
                }
                finally
                {
                    if (held) { try { mutex.ReleaseMutex(); } catch { } }
                    CloseLog();
                }
            }
        }

        private static int Run(string[] args)
        {
            // Any --reap spelling is a subcommand, however many arguments follow.
            // Matching only on args.Length == 1 meant "--reap /some/file" fell
            // through and cold-started Affinity instead.
            if (args.Length > 0 && (args[0] == "--reap" || args[0] == "--reap-dry-run"))
            {
                bool dryRun = args[0] == "--reap-dry-run";
                int n = ReapSpentInstances(dryRun);
                Log("reaper: " + n + (dryRun ? " process(es) would be reaped" : " process(es) reaped"));
                // Say whether anything was found, so a script can branch on it.
                // Always returning 0 made "nothing to reap" and "cleared a
                // corpse" indistinguishable.
                return n > 0 ? 0 : 1;
            }

            string dir = FindAffinityDirectory();
            if (dir == null)
            {
                Fail("Could not find Affinity.exe");
                return 1;
            }

            string affinity = Path.Combine(dir, "Affinity.exe");
            string hook = Path.Combine(dir, "AffinityHook.exe");
            bool hasHook = File.Exists(hook);
            string launcher = hasHook ? hook : affinity;

            Log("affinity=" + affinity + " hook=" + (hasHook ? hook : "(not installed)"));

            var docs = new List<string>();
            int failed = 0;
            foreach (string a in args)
            {
                string dos = ToDosPath(a);
                if (dos == null) { Note("Cannot map to a Windows path: " + a); failed = 1; continue; }
                if (!File.Exists(dos)) { Note("No such file: " + a); failed = 1; continue; }
                docs.Add(dos);
            }
            if (args.Length > 0 && docs.Count == 0) return failed;

            // Clear a corpse BEFORE asking whether Affinity is running. A process
            // that logged "Exit" and then hung still answers "running", and it
            // cannot take a handoff -- so without this every launch is handed to
            // a dead instance and silently does nothing. This supersedes
            // FindHusks() for the 3.3 zombie: the log is evidence, a thread count
            // is a guess. FindHusks stays as the fallback for a process that left
            // no "Exit" behind, such as one that crashed.
            ReapSpentInstances(false);

            if (IsAffinityRunning())
            {
                // Warm. Straight to Affinity.exe -- see the header. Affinity's
                // singleton forwards the document and brings itself forward.
                if (docs.Count == 0)
                {
                    Log("warm: bare launch, nudging the running instance");
                    StartAndWait(affinity, "", 20);
                }
                else
                {
                    foreach (string d in docs)
                    {
                        Log("warm handoff: " + d);
                        if (!HandOff(affinity, d, 2)) failed = 1;
                    }
                }
                return failed;
            }

            return ColdStart(launcher, affinity, hasHook, docs) ? failed : 1;
        }

        // ---------------------------------------------------------------- cold

        // TWO-STAGE COLD START
        //
        // A cold start goes through AffinityHook.exe so plugins load, and the
        // hook forwards its arguments with string.Join(" ", args). A path
        // containing a space therefore arrives at Affinity split into fragments,
        // one "failed to open" dialog each.
        //
        // Rather than depend on a patched hook -- or pre-quote to match the
        // unpatched one, which then breaks against a patched one -- side-step
        // the hook's argument handling entirely for those paths: start the hook
        // with no document at all, wait until the window is up, and then hand
        // the document over exactly as a warm handoff would. That behaves the
        // same against a vanilla AffinityPluginLoader and a patched one.
        //
        // 8.3 short paths were tried first and rejected: they open the right
        // file, but Affinity keeps the short name as the document's identity
        // (the lock sidecar comes out as BRAN~ECI.AF~lock~), so the tab and
        // Recent Documents would show it too.
        private static bool ColdStart(string launcher, string affinity, bool viaHook, List<string> docs)
        {
            bool needsTwoStage = viaHook && docs.Exists(NeedsQuoting);
            bool opened = true;
            string arguments = needsTwoStage ? "" : JoinQuoted(docs);

            // Husks from a previous close still own the single-instance
            // registration. Left alone, the two-stage handoff below hands the
            // document to one of them and it is silently dropped.
            List<Process> husks = FindHusks();
            if (husks.Count > 0)
            {
                Log("clearing " + husks.Count + " husk process(es) left by a previous close");
                foreach (Process h in husks)
                {
                    // Wait for each one. A fixed sleep assumes the kill landed;
                    // if it did not, Start() below adds a SECOND instance to a
                    // still-running one, which is the thing this program exists
                    // to prevent. Say so rather than continuing quietly.
                    try
                    {
                        h.Kill();
                        if (!h.WaitForExit(HuskKillWaitMs))
                            Note("husk " + h.Id + " did not die; not starting a rival");
                    }
                    catch { }
                }
            }

            Log("cold start: launcher=" + Path.GetFileName(launcher)
                + " twoStage=" + needsTwoStage + " args=[" + arguments + "]");

            Process child = Start(launcher, arguments);
            if (child == null) { Note("could not start " + launcher); return false; }

            // The two-stage handoff has nothing to hand to until the window is
            // up, so this path still waits for one. It no longer kills anything
            // if the window never appears -- hand the document over regardless
            // and let Affinity deal with it.
            if (needsTwoStage)
            {
                if (WaitForStartup(child) != 1)
                    Note("no window after " + StallSeconds + "s; handing the document over anyway");
                foreach (string d in docs)
                {
                    Log("cold two-stage handoff: " + d);
                    // Report it. Discarding this made a cold launch that never
                    // opened the document exit 0, so a caller had no way to know.
                    if (!HandOff(affinity, d, 3)) opened = false;
                }
            }
            return opened;
        }

        // RETIRED 2026-09-16 -- the retry watchdog, kept for reference.
        //
        // It was written for a startup deadlock that was real when it was
        // measured: roughly one launch in three stalled during initialisation,
        // vkd3d-proton creating the D3D12 device and then nothing, and a fresh
        // launch always cleared it. bin/affinity-launch carries the numbers.
        //
        // It is retired because it stopped catching that and started causing
        // harm. Every stall it has ever logged is in one prefix and on one day,
        // and each time it failed all three attempts and gave up -- which an
        // intermittent one-in-three hang does with probability 0.037, twice in
        // a day with probability 0.0014. It was not detecting a hang. It was
        // failing to recognise a window that was up, because FindAffinityWindow
        // required GetWindowRect to report at least 600 pixels of width and
        // Affinity 3.3's main window reported left = 22369618 and a NEGATIVE
        // width, while X reported a perfectly sane 3850x2101 for the same
        // window. (It measures the client rect now, which is sane.) So it killed a running Affinity the user was working in,
        // three times over, at exactly StallSeconds each.
        //
        // Score at retirement: 31 recorded cold starts in the working prefix
        // with zero stalls, against at least two live sessions killed. If the
        // old hang ever returns, bring this back -- but fix the detection
        // first: do not trust the rect, and re-check that Affinity really is
        // not running before killing anything.
        //
        //     for (int attempt = 1; attempt <= MaxTries; attempt++)
        //     {
        //         Process child = Start(launcher, arguments);
        //         if (child == null) { Note("could not start " + launcher); return false; }
        //
        //         int outcome = WaitForStartup(child);
        //         if (outcome == 1)
        //         {
        //             if (attempt > 1) Note("started on attempt " + attempt);
        //             if (needsTwoStage)
        //                 foreach (string d in docs)
        //                 {
        //                     Log("cold two-stage handoff: " + d);
        //                     HandOff(affinity, d, 3);
        //                 }
        //             return true;
        //         }
        //
        //         Note(outcome == 2
        //             ? "exited during startup (attempt " + attempt + "/" + MaxTries + ") -- retrying"
        //             : "startup stalled (attempt " + attempt + "/" + MaxTries + ") -- retrying");
        //         KillAffinity(child);
        //     }
        //
        //     Note("failed to start after " + MaxTries + " attempts; launching without the watchdog");
        //     Start(launcher, arguments);
        //     return true;


        // Hand a document over and confirm it arrived.
        //
        // The handoff is a race against Affinity finishing its startup. The
        // forwarding process exits 0 either way -- it has done its job once the
        // command line is delivered -- so its exit code says nothing about
        // whether the document opened. Watched failing: the instance was 17
        // seconds old and 24 threads into a startup that ends near 150, the
        // forward was accepted, and the document was dropped.
        //
        // Affinity writes "<document>~lock~" beside a document it has open, so
        // that file is the answer. Where one already exists -- a crash leaves
        // them behind -- there is nothing to watch for, and the handoff is made
        // once without confirmation rather than guessing.
        // Is this document open? Affinity marks one with a "<doc>~lock~" sidecar
        // -- and then sets a Dropbox "ignore" attribute on that sidecar, which is
        // an NTFS alternate data stream. Wine materialises a stream as a separate
        // file named "<name>:<stream>", so what is actually on disk beside an open
        // document is
        //
        //     <doc>~lock~:com.dropbox.ignored
        //
        // and no plain "<doc>~lock~" at all. Measured across this machine: 193
        // files match "*~lock~*" and exactly one matches "*~lock~".
        //
        // So File.Exists(doc + "~lock~") answers "no" for a document that is open
        // on screen. The handoff was retried until it ran out of attempts -- each
        // retry asking Affinity to open the document again -- and the user was
        // told "Affinity did not open <doc>" while looking at it.
        //
        // A stale marker (Wine leaves these behind when the base file goes) then
        // reads as "already open", which is the case HandOff already handles by
        // making one handoff and not retrying.
        //
        // The directory is listed rather than globbed: ":" is not legal in a
        // search pattern and throws.
        private static bool LockPresent(string doc)
        {
            string lockFile = doc + "~lock~";
            if (File.Exists(lockFile)) return true;

            try
            {
                string dir = Path.GetDirectoryName(lockFile);
                if (dir == null) return false;

                // Compare the WHOLE path. Path.GetFileName must not touch these
                // names: ':' is Path.VolumeSeparatorChar, and both .NET Framework
                // and Mono stop at it, so GetFileName of
                //     ...\doc.af~lock~:com.dropbox.ignored
                // returns "com.dropbox.ignored". Written the obvious way, with
                // GetFileName on both sides, this branch never matched anything
                // and the whole fix was dead code. Measured under Wine, not
                // reasoned about: a probe printed GetFileName -> com.dropbox.ignored
                // and the comparison false for a marker sitting right there.
                string marker = lockFile + ":";
                foreach (string f in Directory.GetFiles(dir))
                    if (f.Length > marker.Length &&
                        f.StartsWith(marker, StringComparison.OrdinalIgnoreCase))
                        return true;
            }
            catch { }
            return false;
        }

        private static bool HandOff(string affinity, string doc, int tries)
        {
            bool preexisting = LockPresent(doc);

            for (int attempt = 1; attempt <= tries; attempt++)
            {
                StartAndWait(affinity, Quote(doc), 30);
                if (preexisting) return true;         // cannot tell; do not retry

                for (int i = 0; i < 20; i++)
                {
                    Thread.Sleep(1000);
                    if (LockPresent(doc))
                    {
                        if (attempt > 1) Log("opened on attempt " + attempt);
                        return true;
                    }
                }
                if (attempt < tries)
                    Log("no lock file after the handoff; Affinity was probably still "
                        + "starting -- retrying (" + (attempt + 1) + "/" + tries + ")");
            }
            Note("Affinity did not open " + Path.GetFileName(doc));
            return false;
        }

        // 1 = a window came up, 2 = the child exited first, 0 = stalled.
        private static int WaitForStartup(Process child)
        {
            for (int i = 0; i < StallSeconds; i++)
            {
                Thread.Sleep(1000);
                if (FindAffinityWindow() != IntPtr.Zero) return 1;
                try { if (child.HasExited) return 2; } catch { return 2; }
            }
            return 0;
        }

        // Only ever this prefix's processes: inside Wine, Process.GetProcesses()
        // cannot see anything else. That is also why this program can never fall
        // into the `pgrep -f Affinity.exe matches my own shell` trap.
        // RETIRED with the watchdog above -- nothing calls this now.
        // private static void KillAffinity(Process child)
        // {
        //     try { if (!child.HasExited) child.Kill(); } catch { }
        //     foreach (string name in new[] { "Affinity", "AffinityHook" })
        //         foreach (Process p in SafeGetProcesses(name))
        //             try { p.Kill(); } catch { }
        //     Thread.Sleep(2000);
        // }

        // ------------------------------------------------------------- the reaper

        // THE SHUTDOWN ZOMBIE
        //
        // Affinity 3.3 does not exit. It closes its windows, flushes its
        // settings, logs "Exit" -- and then deadlocks in libnetwork.dll's
        // DllMain(DLL_PROCESS_DETACH) and sits there with ~2GB resident and 0%
        // CPU until the machine reboots. IsAffinityRunning() answers "running"
        // for that corpse, and the corpse cannot take a handoff, so every launch
        // after it is handed over and appears to do nothing at all. "Affinity
        // won't start" is nearly always this.
        //
        // 3.2.3 does not do it. WINEDEBUG=+module prints a CALL and a RETURN
        // around every DllMain: 3.2.3 gives 517 detach calls and 517 returns,
        // 3.3.0.4850 gives 190 and 189, and the missing return is libnetwork's.
        // It is Affinity's own DLL and no Wine-side setting influences it. Full
        // workings, and three explanations that fit and are wrong, in
        // docs/shutdown-zombie-libnetwork.md.
        //
        // Killing such a process loses nothing. Settings\*.xml, studios3.dat,
        // sess.db, preferences.dat and the IPC shutdown all complete BEFORE the
        // hang, and the "Exit" line is written 0.2-1s after them. "Exit" is the
        // application's own statement that it has finished.
        //
        // A process is spent only if ALL THREE of these hold:
        //
        //   1. it is an Affinity.exe. Running inside the prefix,
        //      Process.GetProcessesByName sees only this prefix's processes --
        //      so unlike a host-side reaper there is no WINEPREFIX to parse and
        //      no way to stray into another prefix. The condition is structural.
        //   2. it owns no visible top-level window. Invisible ones outlive the
        //      UI -- see ProcessOwnsAVisibleWindow for what a corpse still holds.
        //   3. the app log records "Exit" at or after the moment that process
        //      started.
        //
        // Condition 3 is the one that is easy to leave out and expensive to get
        // wrong. Log.txt is truncated at startup, so a running instance has no
        // "Exit" in it at all -- but between a process appearing and the log
        // being rewritten, the PREVIOUS run's "Exit" is still on disk and the new
        // process has no window yet. Conditions 1 and 2 alone kill a healthy
        // Affinity during its own startup.
        //
        // It also makes the two-process case come out right on its own: with a
        // corpse and a live instance side by side, the corpse started before the
        // logged "Exit" and the live one after it, so exactly the corpse is
        // reaped. That only holds because reaping happens BEFORE anything is
        // started -- a new Affinity truncates Log.txt and takes the evidence
        // with it.
        //
        // Everything undeterminable -- an unreadable log, an unparseable stamp,
        // a process that will not give its start time -- counts as "leave it
        // alone".

        private const int ReapWaitMs = 10000;   // for the kill to take effect

        private static int ReapSpentInstances(bool dryRun)
        {
            DateTime exitedAt;
            string why;
            if (!TryReadLoggedExit(out exitedAt, out why))
            {
                // Say WHICH of these it was. One of these refusals was seen once
                // and could not be reproduced -- six consecutive runs against the
                // same corpse then succeeded -- and with a single message there
                // was no way to tell a missing log from an unreadable one from a
                // log with no Exit in it. The refusal is fail-safe either way: it
                // declines to reap, it never kills on a bad read.
                Log("reaper: " + why + " -- nothing here can be spent");
                return 0;
            }

            int reaped = 0;
            foreach (Process p in SafeGetProcesses("Affinity"))
            {
                int pid;
                try { pid = p.Id; }
                catch { continue; }

                if (ProcessOwnsAVisibleWindow(pid))
                {
                    Log("reaper: pid " + pid + " owns a visible window -- leaving it alone");
                    continue;
                }

                DateTime startedAt;
                try { startedAt = p.StartTime; }
                catch (Exception e)
                {
                    Log("reaper: pid " + pid + " start time unreadable (" + e.Message + ") -- leaving it alone");
                    continue;
                }

                if (exitedAt < startedAt)
                {
                    Log("reaper: pid " + pid + " started at " + Stamp(startedAt) + ", after the Exit at "
                        + Stamp(exitedAt) + " -- it is still starting up, leaving it alone");
                    continue;
                }

                if (dryRun)
                {
                    Log("reaper: would reap pid " + pid + " -- no windows, started " + Stamp(startedAt)
                        + ", logged Exit " + Stamp(exitedAt));
                    reaped++;
                    continue;
                }

                Note("clearing a leftover Affinity (pid " + pid + ") that logged Exit and then failed to leave");
                try
                {
                    // WaitForExit returning true is the in-prefix truth: the
                    // wineserver has released the process and Affinity's
                    // singleton is free, which is all the next launch needs. The
                    // underlying Unix task can linger a moment longer -- it is
                    // blocked in a futex inside a DllMain, and that is the whole
                    // bug -- so a check made immediately afterwards from outside
                    // the prefix can still see it. Measured: gone within seconds.
                    p.Kill();
                    if (p.WaitForExit(ReapWaitMs)) reaped++;
                    else Note("pid " + pid + " did not die within " + (ReapWaitMs / 1000) + "s");
                }
                catch (Exception e)
                {
                    Note("could not clear pid " + pid + ": " + e.Message);
                }
            }
            return reaped;
        }

        // Does this process own a VISIBLE top-level window?
        //
        // Deliberately not FindAffinityWindow(). That one asks a different
        // question -- is the titled, wide main window up -- and until 2026-10-01
        // it answered it with GetWindowRect, which for Affinity 3.3's main window
        // reports left = 22369618 and a NEGATIVE width under Wine while X reports
        // a perfectly sane 3850x2101. Trusting that rect is exactly what made the
        // retired watchdog kill three live sessions. A kill path asks only
        // whether ANY visible window is owned, which needs no geometry at all.
        //
        // Nor is it "any window at all", which was the first attempt here and is
        // useless: measured against a real corpse, a spent Affinity still owns
        // three top-level windows, all of them invisible infrastructure that
        // outlives the UI --
        //
        //     .NET-BroadcastEventWindow.4.0.0.0.<hash>   WPF's message sink
        //     "Wine IME"          1x1
        //     "Default IME"       1x1
        //
        // -- so that test never reaps anything. WS_VISIBLE is what separates
        // them: the same measurement on a healthy instance shows a visible
        // HwndWrapper[Affinity.exe;;<guid>], and a corpse shows none.
        //
        // Visibility, not a title and not a size. The healthy window measured
        // here was UNTITLED (587x450, the welcome window), so requiring a title
        // would have called a live session spent. A minimised or off-desktop
        // window keeps WS_VISIBLE, so neither of those is mistaken for a corpse
        // either. And a process in the first seconds of startup, before its
        // first window is shown, is covered by condition 3 rather than this one.
        //
        // A failed enumeration counts as "yes, it has one".
        private static bool ProcessOwnsAVisibleWindow(int pid)
        {
            bool found = false;
            bool complete = EnumWindows((hwnd, lp) =>
            {
                if (!IsWindowVisible(hwnd)) return true;
                int owner;
                GetWindowThreadProcessId(hwnd, out owner);
                if (owner != pid) return true;
                found = true;
                return false;               // stop; one is enough
            }, IntPtr.Zero);

            // EnumWindows returns false both when the callback stopped it and
            // when it failed. Only the second is ambiguous, and it must not read
            // as "this process has no windows".
            if (!complete && !found) return true;
            return found;
        }

        // %APPDATA%\Affinity\Affinity\<version>\Log.txt. The version folder is
        // 3.0 today and will not always be, so take the most recently written.
        private static string FindAppLog()
        {
            try
            {
                string root = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "Affinity", "Affinity");
                if (!Directory.Exists(root)) return null;

                string newest = null;
                DateTime newestAt = DateTime.MinValue;
                foreach (string dir in Directory.GetDirectories(root))
                {
                    string log = Path.Combine(dir, "Log.txt");
                    if (!File.Exists(log)) continue;
                    DateTime at = File.GetLastWriteTime(log);
                    if (newest == null || at > newestAt) { newest = log; newestAt = at; }
                }
                return newest;
            }
            catch { return null; }
        }

        // The last "Exit" the application logged. The line looks like
        //     [2026-09-17T08:28:05.182-04:00] Exit
        private static bool TryReadLoggedExit(out DateTime when, out string why)
        {
            when = DateTime.MinValue;

            string log = FindAppLog();
            if (log == null) { why = "no app log found under %APPDATA%"; return false; }

            string last = null;
            try
            {
                // Share it: a running Affinity holds this file open for writing.
                using (var fs = new FileStream(log, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var reader = new StreamReader(fs))
                {
                    string line;
                    while ((line = reader.ReadLine()) != null)
                        if (line.IndexOf("] Exit", StringComparison.Ordinal) > 0) last = line;
                }
            }
            catch (Exception e) { why = "could not read " + log + " (" + e.Message + ")"; return false; }

            if (last == null) { why = "the app log records no Exit"; return false; }
            if (last.Length == 0 || last[0] != '[') { why = "the Exit line has no timestamp"; return false; }
            int close = last.IndexOf(']');
            if (close < 2) { why = "the Exit line has no timestamp"; return false; }

            DateTimeOffset stamp;
            if (!DateTimeOffset.TryParse(last.Substring(1, close - 1), CultureInfo.InvariantCulture,
                                         DateTimeStyles.RoundtripKind, out stamp))
            {
                why = "could not parse the Exit stamp " + last.Substring(1, close - 1);
                return false;
            }

            when = stamp.LocalDateTime;
            why = null;
            return true;
        }

        private static string Stamp(DateTime t)
        {
            return t.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
        }

        // -------------------------------------------------------------- helpers

        // A window means a running instance, no argument. Without one, processes
        // alone are ambiguous: Affinity is either on its way up or on its way
        // down, and the two need opposite answers.
        //
        // Closing Affinity leaves husks. Measured while watching a close:
        // 152 threads and a window, then moments later processes at three
        // threads, no window, no document -- and they linger. Treating those as
        // "running" sends the document to a dying process, which discards it,
        // and the forward then starts an instance of its own WITHOUT the
        // document. That is the blank window with no tab.
        //
        // Thread count alone will not separate them. A live instance runs at
        // 150+ and one still starting passes fifty within seconds, but a
        // closing one descends through every value on its way down -- caught at
        // 17 once. So a count is only ever used as proof of life, never as
        // proof of death.
        //
        // The asymmetry decides the rest. Mistaking a husk for a live instance
        // costs an unopened document; mistaking a live instance for a husk
        // kills the user's session and whatever was unsaved in it. So a
        // process is only ever declared dead after it has been given the whole
        // startup window to produce one, which anything genuinely starting
        // will.
        private const int LiveThreadFloor = 40;

        // How long to wait for a husk kill to land before saying so.
        private const int HuskKillWaitMs = 10000;

        private static bool AnyLiveByThreads()
        {
            foreach (Process p in SafeGetProcesses("Affinity"))
                if (ThreadCount(p) >= LiveThreadFloor) return true;
            return false;
        }

        private static bool AnyAffinityProcess()
        {
            foreach (string name in new[] { "Affinity", "AffinityHook" })
                if (SafeGetProcesses(name).Length > 0) return true;
            return false;
        }

        private static bool IsAffinityRunning()
        {
            if (FindAffinityWindow() != IntPtr.Zero) return true;
            if (AnyLiveByThreads()) return true;

            // Processes but no window and no thread count to vouch for them.
            // Either a start in progress -- the hook exists for ~30s before
            // Affinity.exe does, and missing it there is what cold starts a
            // rival on a second double-click -- or husks from a close.
            if (!AnyAffinityProcess()) return false;

            // Age settles it without waiting. A start that has not produced a
            // window yet is seconds old; a husk has been alive since Affinity
            // was started, which is however long the session lasted. Waiting out
            // the startup window instead is correct but costs 46 seconds on
            // every close-then-click, which reads as nothing happening at all.
            if (!AnyStartedRecently())
            {
                Log("processes are older than a startup and have no window; husks");
                return false;
            }

            // StartupGraceSeconds, not StallSeconds. This loop is what lets
            // FindHusks call something a husk, so it has to outlast the window a
            // start is allowed. At 45 against a 75s grace it gave up thirty
            // seconds early and handed a starting Affinity over to be killed.
            Log("recently started processes with no window; waiting to see whether one is starting");
            for (int i = 0; i < StartupGraceSeconds; i++)
            {
                Thread.Sleep(1000);
                if (FindAffinityWindow() != IntPtr.Zero) return true;
                if (AnyLiveByThreads()) return true;
                if (!AnyAffinityProcess()) return false;   // husks reaped themselves
                if (!AnyStartedRecently())
                {
                    Log("no window within a startup; husks");
                    return false;
                }
            }
            Log("no window appeared; treating the remaining processes as husks");
            return false;
        }

        // Long enough for a genuine start to have put a window up. The hook
        // exists for about thirty seconds before Affinity.exe does, so this is
        // measured from the oldest of them and kept generous -- being wrong the
        // other way kills a live session.
        private const int StartupGraceSeconds = 75;

        private static bool AnyStartedRecently()
        {
            foreach (string name in new[] { "Affinity", "AffinityHook" })
                foreach (Process p in SafeGetProcesses(name))
                {
                    try
                    {
                        if ((DateTime.Now - p.StartTime).TotalSeconds < StartupGraceSeconds)
                            return true;
                    }
                    catch
                    {
                        // No start time: say it might be starting. An unopened
                        // document beats killing something that is alive.
                        return true;
                    }
                }
            return false;
        }

        // Husks left behind by a close. They hold Affinity's single-instance
        // registration, so a handoff reaches them instead of a live instance.
        //
        // This is the second of the two places that kill an Affinity, and it used
        // to be the dangerous one. It took two GLOBAL tests -- FindAffinityWindow
        // and AnyLiveByThreads -- and, if neither vouched for anything, returned
        // EVERY Affinity and AffinityHook process for killing, with no per-process
        // test at all. Two things were wrong with that:
        //
        //   * FindAffinityWindow was the rect test. It required GetWindowRect to
        //     report at least 600 pixels of width, and Affinity 3.3's main window
        //     reports left = 22369618 and a NEGATIVE width under Wine. That test
        //     is why the retry watchdog killed three live sessions (see RETIRED
        //     above). Using it as the guard on a kill path repeated the mistake.
        //     It measures the client rect now, and still guards no kill.
        //   * the caller waited StallSeconds (45) before concluding nothing was
        //     alive, while this file's own definition of a startup window is
        //     StartupGraceSeconds (75). A genuine start could be declared a husk
        //     thirty seconds before it was allowed to be.
        //
        // Now every candidate must clear the same bar the reaper uses: it owns no
        // visible window, and it is older than a whole startup window. Anything
        // that cannot be measured counts as alive. AnyLiveByThreads stays as a
        // cheap global short-circuit, never as the deciding vote.
        private static List<Process> FindHusks()
        {
            var husks = new List<Process>();
            if (AnyLiveByThreads()) return husks;

            foreach (string name in new[] { "Affinity", "AffinityHook" })
                foreach (Process p in SafeGetProcesses(name))
                {
                    int pid;
                    try { pid = p.Id; }
                    catch { continue; }

                    if (ProcessOwnsAVisibleWindow(pid))
                    {
                        Log("husk check: pid " + pid + " owns a visible window -- alive");
                        continue;
                    }

                    double age;
                    try { age = (DateTime.Now - p.StartTime).TotalSeconds; }
                    catch
                    {
                        Log("husk check: pid " + pid + " has no readable start time -- assuming alive");
                        continue;
                    }

                    if (age < StartupGraceSeconds)
                    {
                        Log("husk check: pid " + pid + " is " + (int)age + "s old, inside the "
                            + StartupGraceSeconds + "s startup window -- assuming it is starting");
                        continue;
                    }

                    husks.Add(p);
                }
            return husks;
        }

        // Only ever compared against LiveThreadFloor as PROOF OF LIFE, so a count
        // that cannot be read must answer "alive". Returning 0 -- the obvious
        // thing -- turns a failure to measure into proof of death, which is the
        // one direction this file is not allowed to be wrong in.
        private static int ThreadCount(Process p)
        {
            try { return p.Threads.Count; } catch { return int.MaxValue; }
        }

        private static Process[] SafeGetProcesses(string name)
        {
            try { return Process.GetProcessesByName(name); }
            catch { return new Process[0]; }
        }

        private static string FindAffinityDirectory()
        {
            string here = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            if (here != null && File.Exists(Path.Combine(here, "Affinity.exe"))) return here;

            string standard = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Affinity", "Affinity");
            return File.Exists(Path.Combine(standard, "Affinity.exe")) ? standard : null;
        }

        private static Process Start(string exe, string arguments)
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = arguments,
                WorkingDirectory = Path.GetDirectoryName(exe),
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            // OpenCL is left to the prefix registry, which the installer sets
            // per Wine build: opencl="" (off) on 11.11 to 11.18, where it
            // deadlocks Affinity at startup on a real GPU, and nothing from
            // 11.19, where the patch set fixes it. This used to append
            // opencl=d here as well, which kept OpenCL off on every build.
            // WINEDLLOVERRIDES from the launcher or the user passes through
            // untouched.
            try { return Process.Start(psi); }
            catch (Exception ex) { Log("start failed: " + ex.Message); return null; }
        }

        private static int StartAndWait(string exe, string arguments, int seconds)
        {
            Process p = Start(exe, arguments);
            if (p == null) return -1;
            try { return p.WaitForExit(seconds * 1000) ? p.ExitCode : 0; }
            catch { return 0; }
        }

        // ------------------------------------------------------------ path work

        [DllImport("kernel32.dll")] private static extern IntPtr GetProcessHeap();
        [DllImport("kernel32.dll")] private static extern bool HeapFree(IntPtr heap, uint flags, IntPtr mem);

        [DllImport("kernel32.dll", EntryPoint = "wine_get_dos_file_name",
                   CallingConvention = CallingConvention.Cdecl)]
        private static extern IntPtr WineGetDosFileName(IntPtr utf8Path);

        // Wine converts argv[0] to a DOS path but passes arguments through
        // verbatim, so a file manager's /mnt/work/x.afphoto arrives unchanged.
        // wine_get_dos_file_name takes CP_UNIXCP (UTF-8 here), so marshal the
        // bytes rather than letting the runtime use the ANSI code page.
        private static string ToDosPath(string path)
        {
            if (string.IsNullOrEmpty(path)) return null;
            // Ordinal: the default StartsWith is culture-sensitive, and under a
            // culture that does clever things with separators this is the wrong
            // question asked the wrong way. Every other comparison in this file
            // is already ordinal.
            if (!path.StartsWith("/", StringComparison.Ordinal)) return path;

            byte[] utf8 = Encoding.UTF8.GetBytes(path);
            IntPtr buf = Marshal.AllocHGlobal(utf8.Length + 1);
            try
            {
                Marshal.Copy(utf8, 0, buf, utf8.Length);
                Marshal.WriteByte(buf, utf8.Length, 0);
                IntPtr result = WineGetDosFileName(buf);
                if (result == IntPtr.Zero) return null;
                try { return Marshal.PtrToStringUni(result); }
                // Wine documents the buffer as the caller's to free, and
                // kernel32/path.c allocates it with RtlAllocateHeap on the
                // PROCESS heap -- so it is HeapFree, not Marshal.FreeHGlobal.
                // That one calls LocalFree, a different allocator, and handing
                // one allocator's pointer to another is how a free becomes a
                // crash. One leak per document would be nothing, but this is
                // also the warm-handoff path and a file manager can hand it
                // several at once.
                finally { HeapFree( GetProcessHeap(), 0, result ); }
            }
            catch (EntryPointNotFoundException) { return path; }   // not Wine
            catch (DllNotFoundException) { return path; }
            finally { Marshal.FreeHGlobal(buf); }
        }

        private static readonly char[] ArgumentDelimiters = { ' ', '\t', '\n', '\v', '"' };

        private static bool NeedsQuoting(string s)
        {
            return s.Length == 0 || s.IndexOfAny(ArgumentDelimiters) >= 0;
        }

        private static string JoinQuoted(List<string> items)
        {
            var sb = new StringBuilder();
            foreach (string s in items)
            {
                if (sb.Length > 0) sb.Append(' ');
                sb.Append(Quote(s));
            }
            return sb.ToString();
        }

        // ProcessStartInfo.Arguments is handed to CreateProcess and re-parsed
        // with the CommandLineToArgvW rules, so quote to survive that.
        private static string Quote(string arg)
        {
            if (!NeedsQuoting(arg)) return arg;

            var sb = new StringBuilder();
            sb.Append('"');
            for (int i = 0; i < arg.Length; i++)
            {
                int slashes = 0;
                while (i < arg.Length && arg[i] == '\\') { slashes++; i++; }

                if (i == arg.Length) { sb.Append('\\', slashes * 2); break; }
                if (arg[i] == '"') { sb.Append('\\', slashes * 2 + 1); }
                else { sb.Append('\\', slashes); }
                sb.Append(arg[i]);
            }
            sb.Append('"');
            return sb.ToString();
        }

        // ------------------------------------------------------------- windows

        private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassNameW(IntPtr hwnd, StringBuilder buf, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowTextW(IntPtr hwnd, StringBuilder buf, int max);
        [DllImport("user32.dll")] private static extern bool GetClientRect(IntPtr hwnd, out RECT r);
        [DllImport("user32.dll")] private static extern int GetWindowThreadProcessId(IntPtr hwnd, out int pid);

        [StructLayout(LayoutKind.Sequential)]
        private struct RECT { public int Left, Top, Right, Bottom; }

        // Affinity is WPF: its main window class is HwndWrapper[Affinity.exe;;<guid>].
        // Several of those exist -- the real one is visible, titled and wide.
        //
        // Wide by its CLIENT rect. Affinity 3.3's maximised main window reports a
        // window rect of left = 23469763, right = 2017 under Wine -- a negative
        // width -- while its client rect is a sane 2014x1097. Measured with a
        // window probe across a cold start (2026-10-01):
        //
        //      4.2s  splash    untitled  client 587x450
        //     14.4s  main      "Affinity"  window rect garbage, client 2014x1097
        //     17.4s  welcome   untitled  client 1007x734, owned by main
        //
        // With the window rect this never matched on 3.3, so the two-stage cold
        // start waited out all of StallSeconds on every document whose path has
        // a space in it: 50s to open instead of ~17s.
        private static IntPtr FindAffinityWindow()
        {
            IntPtr found = IntPtr.Zero;
            var cls = new StringBuilder(256);
            var txt = new StringBuilder(256);

            EnumWindows((hwnd, lp) =>
            {
                if (!IsWindowVisible(hwnd)) return true;
                cls.Length = 0; txt.Length = 0;
                GetClassNameW(hwnd, cls, cls.Capacity);
                if (cls.ToString().IndexOf("HwndWrapper[Affinity.exe", StringComparison.Ordinal) < 0) return true;
                GetWindowTextW(hwnd, txt, txt.Capacity);
                if (txt.Length == 0) return true;
                RECT r;
                if (!GetClientRect(hwnd, out r) || r.Right - r.Left < 600) return true;
                found = hwnd;
                return false;
            }, IntPtr.Zero);

            return found;
        }

        // ------------------------------------------------------------- logging

        private static void OpenLog()
        {
            try
            {
                string dir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "AffinityOnLinux");
                Directory.CreateDirectory(dir);
                _log = new StreamWriter(Path.Combine(dir, "affinity-on-linux.log"), true) { AutoFlush = true };
            }
            catch { _log = null; }
        }

        private static void CloseLog()
        {
            try { if (_log != null) _log.Dispose(); } catch { }
            _log = null;
        }

        private static void Log(string message)
        {
            try { if (_log != null) _log.WriteLine(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss ") + message); } catch { }
            Console.WriteLine(message);
        }

        private static void Note(string message)
        {
            Log("NOTE: " + message);
            Console.Error.WriteLine("affinity-on-linux: " + message);
        }

        private static void Fail(string message)
        {
            Note(message);
        }
    }
}
