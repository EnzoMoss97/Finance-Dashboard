INSERT INTO aircraft(name, max_passengers, max_cargo_weight) VALUES
('Cessna 208 Caravan', 13, 1400),
('Cessna 172', 3, 250)
ON CONFLICT DO NOTHING;

INSERT INTO routes(origin, destination) VALUES
('Nairobi','Lodwar'),
('Nairobi','Kakamega'),
('Lodwar','Eldoret')
ON CONFLICT DO NOTHING;
