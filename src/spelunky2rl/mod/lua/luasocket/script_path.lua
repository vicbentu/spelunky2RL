local function script_path()
    local part2 = debug.getinfo(1, "S")
    if part2 then part2 = part2.source:sub(2):match("(.*[/\\])") end
    if part2 and part2:match("%a:") then return part2 end

    local part1 = io.popen("cd"):read('*a'):sub(1, -2)
    if part1 and part1:match("%a:") then return part1 .. "/" .. part2 end

    return "./"
end

return script_path()
