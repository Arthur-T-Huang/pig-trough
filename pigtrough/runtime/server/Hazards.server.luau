-- Any part tagged "Hazard" kills characters that touch it.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Tagged = require(ReplicatedStorage:WaitForChild("PigTrough"):WaitForChild("Runtime"):WaitForChild("Tagged"))

Tagged.each("Hazard", function(part)
	if not part:IsA("BasePart") then
		return
	end
	part.Touched:Connect(function(hit)
		local humanoid = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
		if humanoid and humanoid.Health > 0 then
			humanoid.Health = 0
		end
	end)
end)
