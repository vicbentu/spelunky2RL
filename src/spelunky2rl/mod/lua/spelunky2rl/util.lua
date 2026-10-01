-- Small helpers shared by the other modules.
local M = {}

function M.round(x)
    return math.floor(x + 0.5)
end

-- val, or default when val is nil or false
function M.safe(val, default)
    if val then
        return val
    end
    return default
end

return M
