using Mono.Cecil;
using Mono.Cecil.Cil;

/// <summary>
/// Patches Serif.Affinity.dll to bypass the SharedStorageAccessManager reference
/// that causes TypeLoadException under Wine. Wine's RoResolveNamespace is stubbed,
/// so the CLR cannot resolve the WinRT type, crashing the JIT for the entire
/// ProcessCommandLineArguments method (which handles affinity:// OAuth callbacks).
///
/// The patch retargets the brfalse guard before the SSA block to jump past it,
/// skipping the unreachable WinRT code entirely.
///
/// Safe to run repeatedly -- exits early if already patched.
/// Backs up the original on first patch.
/// </summary>
internal class Program
{
    private const string AssemblyFileName = "Serif.Affinity.dll";

    public static int Main(string[] args)
    {
        if (args.Length != 1)
        {
            Console.WriteLine("Error: Please provide the full path to the Affinity DLL to patch.");
            Console.WriteLine($"Usage: dotnet SharedStorageAccessManagerFix.dll \"/path/to/{AssemblyFileName}\"");
            return 1;
        }

        string assemblyPath = args[0];
        string backupPath = assemblyPath + ".bak";

        if (!File.Exists(assemblyPath))
        {
            Console.WriteLine($"Error: Assembly not found at {assemblyPath}");
            return 1;
        }

        var fileInfo = new FileInfo(assemblyPath);
        if (fileInfo.Length == 0)
        {
            Console.WriteLine("Assembly file is empty. Attempting to restore from backup...");
            if (File.Exists(backupPath))
            {
                File.Copy(backupPath, assemblyPath, overwrite: true);
                Console.WriteLine("Restored from backup.");
            }
            else
            {
                Console.WriteLine("No backup available. Cannot proceed.");
                return 1;
            }
        }

        try
        {
            if (!File.Exists(backupPath))
            {
                File.Copy(assemblyPath, backupPath);
                Console.WriteLine($"Created backup at: {backupPath}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error creating backup: {ex.Message}");
            return 1;
        }

        AssemblyDefinition? assembly = null;
        try
        {
            using var resolver = new DefaultAssemblyResolver();
            resolver.AddSearchDirectory(Path.GetDirectoryName(assemblyPath)!);

            var readerParameters = new ReaderParameters
            {
                ReadSymbols = false,
                AssemblyResolver = resolver,
            };

            assembly = AssemblyDefinition.ReadAssembly(assemblyPath, readerParameters);

            // Find the method containing SharedStorageAccessManager
            MethodDefinition? target = null;
            int ssaIdx = -1;

            foreach (var type in assembly.MainModule.GetTypes())
            {
                if (!type.HasMethods) continue;
                foreach (var method in type.Methods)
                {
                    if (!method.HasBody) continue;
                    var insts = method.Body.Instructions;
                    for (int i = 0; i < insts.Count; i++)
                    {
                        if (insts[i].Operand is MethodReference mr &&
                            mr.DeclaringType?.FullName?.Contains("SharedStorageAccessManager") == true)
                        {
                            target = method;
                            ssaIdx = i;
                            break;
                        }
                    }
                    if (target != null) break;
                }
                if (target != null) break;
            }

            if (target == null)
            {
                Console.WriteLine("Already patched (no SharedStorageAccessManager reference found).");
                return 0;
            }

            var instructions = target.Body.Instructions;

            // Find the brfalse before SharedStorageAccessManager that guards entry to the SSA block.
            for (int i = ssaIdx - 1; i >= Math.Max(0, ssaIdx - 15); i--)
            {
                if (instructions[i].OpCode != OpCodes.Brfalse_S && instructions[i].OpCode != OpCodes.Brfalse)
                    continue;

                var currentTarget = (Instruction)instructions[i].Operand;
                int currentTargetIdx = instructions.IndexOf(currentTarget);

                if (currentTargetIdx <= i)
                    continue;

                // If brfalse already targets past the SSA call, it's already patched
                if (currentTargetIdx > ssaIdx)
                {
                    Console.WriteLine("Already patched.");
                    return 0;
                }

                // Find leave instruction after SSA block that is in the same
                // exception handler scope as the brfalse (to avoid producing
                // unverifiable IL that crosses handler boundaries).
                Instruction? leaveInst = null;
                var branchInst = instructions[i];
                for (int j = ssaIdx + 1; j < instructions.Count; j++)
                {
                    if (instructions[j].OpCode != OpCodes.Leave && instructions[j].OpCode != OpCodes.Leave_S)
                        continue;

                    // Verify both the branch and the leave target are in the same handler scope
                    bool sameScope = true;
                    if (target.Body.HasExceptionHandlers)
                    {
                        foreach (var handler in target.Body.ExceptionHandlers)
                        {
                            bool branchInTry = branchInst.Offset >= handler.TryStart.Offset &&
                                               branchInst.Offset < handler.TryEnd.Offset;
                            bool leaveInTry = instructions[j].Offset >= handler.TryStart.Offset &&
                                              instructions[j].Offset < handler.TryEnd.Offset;
                            if (branchInTry != leaveInTry)
                            {
                                sameScope = false;
                                break;
                            }
                        }
                    }

                    if (sameScope)
                    {
                        leaveInst = instructions[j];
                        break;
                    }
                }

                if (leaveInst == null)
                {
                    Console.Error.WriteLine("Error: No leave instruction found after SSA block in the same exception handler scope.");
                    return 1;
                }

                // Retarget brfalse to skip the SSA block
                instructions[i].Operand = leaveInst;
                if (instructions[i].OpCode == OpCodes.Brfalse_S)
                    instructions[i].OpCode = OpCodes.Brfalse;

                string tempPath = assemblyPath + ".tmp";
                try
                {
                    assembly.Write(tempPath);
                    assembly.Dispose();
                    assembly = null;
                    File.Move(tempPath, assemblyPath, overwrite: true);
                    Console.WriteLine("Patched: SharedStorageAccessManager block bypassed.");
                    return 0;
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"Error writing patched assembly: {ex.Message}");
                    if (File.Exists(tempPath)) File.Delete(tempPath);
                    return 1;
                }
            }

            Console.Error.WriteLine("Error: Could not find guard branch to patch.");
            return 1;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error: {ex.Message}");
            return 1;
        }
        finally
        {
            assembly?.Dispose();
        }
    }
}
