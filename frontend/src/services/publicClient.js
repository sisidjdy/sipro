// publicClient — instance axios untuk halaman PUBLIK (showroom tanpa login).
// Dinamai `publicApi` (bukan `api`) dengan sengaja: gate kontrak API hanya memeriksa
// klien staf `api.<method>`, dan halaman publik tidak boleh mengirim token apa pun.
import axios from "axios";

import { API } from "@/services/apiClient";

const publicApi = axios.create({ baseURL: API });

export default publicApi;
