--!strict
-- CollectionService helpers. Generated map parts carry tags + attributes that
-- server scripts bind behaviour to, so geometry and code stay decoupled.
local CollectionService = game:GetService("CollectionService")

local Tagged = {}

-- Calls `callback` for every instance with `tag`, now and when added later.
function Tagged.each(tag: string, callback: (Instance) -> ()): RBXScriptConnection
	for _, instance in CollectionService:GetTagged(tag) do
		task.spawn(callback, instance)
	end
	return CollectionService:GetInstanceAddedSignal(tag):Connect(callback)
end

-- Returns the Player whose character owns `hit`, if any.
function Tagged.playerFromHit(hit: BasePart): Player?
	local model = hit:FindFirstAncestorOfClass("Model")
	if not model then
		return nil
	end
	return game:GetService("Players"):GetPlayerFromCharacter(model)
end

return Tagged
