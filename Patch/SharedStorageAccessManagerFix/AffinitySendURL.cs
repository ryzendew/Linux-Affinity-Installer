using System;
using System.IO;
using System.IO.Pipes;

/// <summary>
/// Sends an affinity:// OAuth callback URL to the running Affinity instance
/// via named pipe IPC. This avoids launching a second Affinity.exe (which
/// would crash due to the SharedStorageAccessManager TypeLoadException).
///
/// The pipe name "Affinity3Release" matches Affinity's SingleInstance pipe
/// (Name + Version + BuildType). The payload mimics SendArgumentsToSingleInstance:
/// "exe-path\narg1\narg2..." -- the receiver splits on '\n' and skips element 0.
/// </summary>
class AffinitySendURL
{
    static int Main(string[] args)
    {
        if (args.Length == 0)
        {
            Console.WriteLine("Usage: AffinitySendURL.exe <url>");
            Console.WriteLine("Sends an affinity:// URL to the running Affinity instance via named pipe.");
            return 1;
        }

        string pipeName = "Affinity3Release";
        string url = args[0];
        string payload = "dummy.exe\n" + url;

        Console.WriteLine("Connecting to pipe: " + pipeName);
        try
        {
            using (var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.Out))
            {
                pipe.Connect(10000);
                Console.WriteLine("Connected! Sending URL...");

                using (var writer = new BinaryWriter(pipe, System.Text.Encoding.UTF8, false))
                {
                    writer.Write(payload);
                }
            }

            Console.WriteLine("Sent successfully: " + url);
            return 0;
        }
        catch (TimeoutException)
        {
            Console.Error.WriteLine("Error: Timed out connecting to Affinity. Is it running?");
            return 1;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Error: " + ex.GetType().Name + ": " + ex.Message);
            return 1;
        }
    }
}
