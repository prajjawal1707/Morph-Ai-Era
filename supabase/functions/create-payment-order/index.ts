import { createClient } from "https://esm.sh/@supabase/supabase-js@2"
import Razorpay from "https://esm.sh/razorpay@latest"
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

// This is a special utility from Razorpay for verification
import crypto from "https://deno.land/std@0.168.0/node/crypto.ts";

console.log("verify-payment-signature function initialized");

serve(async (req) => {
  // 1. Get the payment details from the frontend
  const { order_id, payment_id, signature, user_id } = await req.json();
  const RAZORPAY_KEY_SECRET = Deno.env.get("RAZORPAY_KEY_SECRET")!;

  if (!order_id || !payment_id || !signature || !user_id) {
    return new Response(JSON.stringify({ error: "Missing required fields" }), { status: 400 });
  }

  try {
    // 2. Securely VERIFY the signature
    // We create a "hash" using our secret key
    const body = order_id + "|" + payment_id;
    const expectedSignature = crypto
      .createHmac("sha256", RAZORPAY_KEY_SECRET)
      .update(body.toString())
      .digest("hex");
    
    // Compare our generated signature with the one from Razorpay
    if (expectedSignature === signature) {
      // --- SIGNATURE IS VALID ---
      console.log("Payment signature verified successfully for:", payment_id);

      // 3. Connect to our Supabase database
      const supabaseAdmin = createClient(
        Deno.env.get("SUPABASE_URL")!,
        Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")! // Use the Service Role Key for admin tasks
      );

      // 4. Get the user's current credits
      const { data: profile, error: fetchError } = await supabaseAdmin
        .from("profiles")
        .select("credits")
        .eq("id", user_id)
        .single();

      if (fetchError || !profile) {
        throw new Error("User profile not found or error fetching: " + fetchError?.message);
      }

      // 5. Add the new credits
      const currentCredits = profile.credits || 0;
      const newCreditTotal = currentCredits + 50; // Add 50 credits

      // 6. Update the database
      const { error: updateError } = await supabaseAdmin
        .from("profiles")
        .update({ credits: newCreditTotal })
        .eq("id", user_id);

      if (updateError) {
        throw new Error("Failed to update credits in database: " + updateError.message);
      }

      console.log(`Credits updated for user ${user_id}. New total: ${newCreditTotal}`);
      
      // 7. Return success to the frontend
      return new Response(JSON.stringify({ status: "success", newCredits: newCreditTotal }), { status: 200 });

    } else {
      // --- SIGNATURE IS FAKE/INVALID ---
      throw new Error("Invalid payment signature");
    }
  } catch (error) {
    console.error("Verification Error:", error.message);
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
});