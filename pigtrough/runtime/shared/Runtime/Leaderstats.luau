--!strict
local Leaderstats = {}

-- Creates the leaderstats folder with an IntValue per name (in display order).
function Leaderstats.setup(player: Player, names: { string }): Folder
	local folder = Instance.new("Folder")
	folder.Name = "leaderstats"
	for _, name in names do
		local value = Instance.new("IntValue")
		value.Name = name
		value.Parent = folder
	end
	folder.Parent = player
	return folder
end

function Leaderstats.get(player: Player, name: string): IntValue?
	local folder = player:FindFirstChild("leaderstats")
	local value = folder and folder:FindFirstChild(name)
	if value and value:IsA("IntValue") then
		return value
	end
	return nil
end

function Leaderstats.add(player: Player, name: string, amount: number)
	local value = Leaderstats.get(player, name)
	if value then
		value.Value += amount
	end
end

return Leaderstats
