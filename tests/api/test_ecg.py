class TestEcg:
    def test_list_returns_every_recording_without_samples(self, client):
        response = client.get("/api/ecg")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert "samples_json" not in body[0]
        assert "points" not in body[0]
        by_date = {row["recorded_local_date"]: row for row in body}
        assert by_date["2026-06-01"]["classification"] == "Sinus Rhythm"
        assert by_date["2026-06-15"]["classification"] == "Inconclusive"
        assert by_date["2026-06-15"]["symptoms"] == "Rapid Heartbeat"

    def test_list_ordered_most_recent_first(self, client):
        response = client.get("/api/ecg")
        body = response.json()
        assert [row["recorded_local_date"] for row in body] == ["2026-06-15", "2026-06-01"]

    def test_date_range_filter(self, client):
        response = client.get("/api/ecg?start=2026-06-10")
        body = response.json()
        assert len(body) == 1
        assert body[0]["recorded_local_date"] == "2026-06-15"

    def test_detail_returns_metadata_and_points(self, client):
        list_response = client.get("/api/ecg")
        recording_id = next(
            row["id"] for row in list_response.json() if row["recorded_local_date"] == "2026-06-01"
        )

        response = client.get(f"/api/ecg/{recording_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["classification"] == "Sinus Rhythm"
        assert body["lead"] == "Lead I"
        assert body["unit"] == "µV"
        assert body["sample_rate"] == 512.0
        assert body["sample_count"] == 250
        # 250 samples is under the default 2000-point cap, so this is a passthrough --
        # every sample comes back, in order, none dropped.
        assert len(body["points"]) == 250
        assert body["points"][0] == {"t": 0.0, "value": 999.0}

    def test_detail_downsamples_when_max_points_is_small(self, client):
        list_response = client.get("/api/ecg")
        recording_id = next(
            row["id"] for row in list_response.json() if row["recorded_local_date"] == "2026-06-01"
        )

        response = client.get(f"/api/ecg/{recording_id}?max_points=100")
        assert response.status_code == 200
        body = response.json()
        assert len(body["points"]) <= 100
        assert len(body["points"]) < 250  # actually reduced, not a passthrough
        # The spike at index 0 (999.0, far outside the 0.0-3.0 oscillation everywhere else)
        # must survive min/max-per-bucket decimation even though most samples are dropped.
        assert body["points"][0] == {"t": 0.0, "value": 999.0}

    def test_unknown_id_is_a_404(self, client):
        response = client.get("/api/ecg/999999")
        assert response.status_code == 404
